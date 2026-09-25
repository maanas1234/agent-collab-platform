"""A scripted AI agent that connects to the platform exactly like a real
coding agent (Claude Code, Codex, Antigravity) would: over MCP. Each turn it
picks one action — discuss, propose a task, claim one, write/commit real
code for a task it owns, or mark progress — standing in for a teammate whose
own agent isn't installed on the demo machine.

The action-type choice (which of ~6 things to do) is answered by a typed
decision model (Jev, hosted, or Laya, local — see jev.py) instead of a full
LLM call, when one is configured. That's a System-1 decision, not
generation, and Jev/Laya answer it directly as calibrated probabilities in
milliseconds. The LLM (via ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL) is still
used for anything that needs actual content: task descriptions, discussion
text, and file contents. If no typed-decision backend is configured, this
falls back to asking the LLM to pick the action too, exactly as before.

Usage: python simulate_agent.py --role backend --name "Backend-Agent"
"""
import argparse
import asyncio
import json
import os

from anthropic import AsyncAnthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import jev

MCP_URL = "http://localhost:8001/mcp"
MODEL = os.environ.get("SIMULATE_AGENT_MODEL", "claude-haiku-4-5-20251001")
TURN_PAUSE_SECONDS = float(os.environ.get("SIMULATE_AGENT_TURN_PAUSE", "0.4"))

SYSTEM = """You are an AI coding agent representing one member of a small dev \
team. Your assigned role: {role}. You share a workspace with other AI agents \
(possibly running different tools) via a PRD, a discussion thread, a task \
board, and a real shared git repo you can read and write files in. Each \
turn, look at the PRD, the discussion, the task board, and the repo, then \
choose exactly ONE action to move the project forward without duplicating \
work others already claimed or already committed. Reply with ONLY a JSON \
object, one of:
{{"action": "post_message", "text": "..."}}
{{"action": "propose_task", "title": "...", "description": "...", "role": "..."}}
{{"action": "claim_task", "task_id": <int>}}
{{"action": "write_code", "task_id": <int>, "path": "...", "content": "...", "message": "..."}}
{{"action": "update_task_status", "task_id": <int>, "status": "in_progress"|"done"}}
{{"action": "noop"}}
Prefer claiming an open task matching your role over proposing a new one if \
one already exists. Prefer writing real code for a task you own over just \
talking about it. Keep messages short."""

CONTENT_PROMPT = {
    "propose_task": (
        "Propose ONE new task for your role that isn't already covered by an "
        'open/claimed task. Reply with ONLY: {{"title": "...", "description": "..."}}'
    ),
    "write_code": (
        "You own task #{task_id} ({task_title}): {task_description}\n"
        "Write ONE file's worth of real, working code for it — check the repo "
        "file list/contents in the state above first so you don't duplicate or "
        "contradict what a teammate already committed. Reply with ONLY: "
        '{{"path": "...", "content": "...", "message": "one-line commit message"}}'
    ),
    "post_message": (
        'Post a short discussion message. Reply with ONLY: {{"text": "..."}}'
    ),
}


def _state_text(role: str, prd: str, tasks: list, messages: list, repo_files: list) -> str:
    return (
        f"Role: {role}\nPRD:\n{prd}\n\nTasks:\n{json.dumps(tasks, indent=2)}\n\n"
        f"Repo files: {repo_files}\n\n"
        f"Recent discussion:\n{json.dumps(messages[-10:], indent=2)}"
    )


async def call(session: ClientSession, name: str, **kwargs):
    result = await session.call_tool(name, kwargs)
    data = result.structuredContent if result.structuredContent is not None else json.loads(result.content[0].text)
    if isinstance(data, dict) and list(data.keys()) == ["result"]:
        return data["result"]
    return data


async def ask_llm(client: AsyncAnthropic, system: str, user: str) -> dict:
    """Retries a couple times — the local proxy occasionally drops the auth
    header under concurrent load ("Could not resolve authentication method"
    even with a valid key) — rather than forcing agents to run one at a time
    just to dodge it."""
    resp = None
    last_err = None
    for attempt in range(3):
        try:
            resp = await client.messages.create(
                model=MODEL, max_tokens=500, system=system,
                messages=[{"role": "user", "content": user}],
            )
            break
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.5 * (attempt + 1))
    if resp is None:
        print(f"  (LLM call failed after retries: {last_err})")
        return {}

    text_blocks = [b.text for b in resp.content if b.type == "text"]
    text = text_blocks[0].strip() if text_blocks else ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def pick_open_task(tasks: list, role: str) -> dict | None:
    for t in tasks:
        if t["status"] == "open" and t["role"] in (role, "general"):
            return t
    return None


def pick_owned_task(tasks: list, agent_id: int, statuses: tuple[str, ...]) -> dict | None:
    for t in tasks:
        if t.get("owner_agent_id") == agent_id and t["status"] in statuses:
            return t
    return None


async def decide(
    client: AsyncAnthropic, role: str, agent_id: int, prd: str, tasks: list, messages: list, repo_files: list
) -> dict:
    state_text = _state_text(role, prd, tasks, messages, repo_files)
    kind = jev.choose_action(state_text)

    if kind is None:
        # No typed-decision backend configured — fall back to asking the LLM
        # to pick the action too, in one call, as before.
        return await ask_llm(client, SYSTEM.format(role=role), state_text)

    if kind == "noop":
        return {"action": "noop"}

    if kind == "claim_task":
        task = pick_open_task(tasks, role)
        if task:
            return {"action": "claim_task", "task_id": task["id"]}
        kind = "propose_task"  # nothing open to claim — fall through to proposing one

    if kind == "update_task_status":
        in_progress = pick_owned_task(tasks, agent_id, ("in_progress",))
        has_commit = any(
            m.get("agent_id") == agent_id and f"task #{in_progress['id']}" in m.get("body", "")
            for m in messages
        ) if in_progress else False
        if in_progress and has_commit:
            return {"action": "update_task_status", "task_id": in_progress["id"], "status": "done"}
        claimed = pick_owned_task(tasks, agent_id, ("claimed",))
        if claimed:
            return {"action": "update_task_status", "task_id": claimed["id"], "status": "in_progress"}
        return {"action": "noop"}

    if kind == "write_code":
        task = pick_owned_task(tasks, agent_id, ("claimed", "in_progress"))
        if not task:
            return {"action": "noop"}
        prompt = CONTENT_PROMPT["write_code"].format(
            task_id=task["id"], task_title=task["title"], task_description=task["description"],
        )
        content = await ask_llm(client, SYSTEM.format(role=role), f"{state_text}\n\n{prompt}")
        if not content.get("path") or not content.get("content"):
            return {"action": "noop"}
        return {"action": "write_code", "task_id": task["id"], **content}

    if kind in ("propose_task", "post_message"):
        content = await ask_llm(client, SYSTEM.format(role=role), f"{state_text}\n\n{CONTENT_PROMPT[kind]}")
        if kind == "propose_task" and not content.get("title"):
            return {"action": "noop"}
        if kind == "post_message" and not content.get("text"):
            return {"action": "noop"}
        return {"action": kind, "role": role, **content}

    return {"action": "noop"}


async def main(role: str, name: str, turns: int) -> None:
    # A stalled request with no timeout can hang a whole run indefinitely —
    # fail fast so the retry loop in ask_llm() actually gets a chance to run.
    client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"), timeout=20.0)

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            joined = await call(session, "register_agent", display_name=name, agent_type="generic")
            agent_id, prd = joined["agent_id"], joined["prd"]
            print(f"[{name}] joined as agent {agent_id}")

            if not joined.get("started"):
                print(f"[{name}] waiting for workspace to start...")
                while not await call(session, "is_started", agent_id=agent_id):
                    await asyncio.sleep(1.5)
                print(f"[{name}] workspace started — beginning work")

            for turn in range(turns):
                tasks = await call(session, "list_tasks", agent_id=agent_id)
                messages = await call(session, "list_messages", agent_id=agent_id)
                repo_files = await call(session, "list_repo_files", agent_id=agent_id)
                action = await decide(client, role, agent_id, prd, tasks, messages, repo_files)
                kind = action.get("action", "noop")
                print(f"[{name}] turn {turn + 1}: {kind}")

                if kind == "post_message":
                    await call(session, "post_message", agent_id=agent_id, text=action["text"])
                elif kind == "propose_task":
                    if action.get("title"):
                        await call(
                            session, "propose_task", agent_id=agent_id,
                            title=action["title"], description=action.get("description", ""),
                            role=action.get("role", role),
                        )
                elif kind == "claim_task":
                    await call(session, "claim_task", agent_id=agent_id, task_id=action["task_id"])
                elif kind == "write_code":
                    result = await call(
                        session, "write_file", agent_id=agent_id, task_id=action["task_id"],
                        path=action["path"], content=action["content"], message=action.get("message", ""),
                    )
                    if not result.get("ok"):
                        print(f"  (write_code rejected: {result.get('error')})")
                elif kind == "update_task_status":
                    await call(
                        session, "update_task_status", agent_id=agent_id,
                        task_id=action["task_id"], status=action["status"],
                    )

                await asyncio.sleep(TURN_PAUSE_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--turns", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(main(args.role, args.name or f"{args.role.title()}-Agent", args.turns))
