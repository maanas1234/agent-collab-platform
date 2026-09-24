"""A scripted AI agent that connects to the platform exactly like a real
coding agent (Claude Code, Codex, Antigravity) would: over MCP. It uses the
Claude API to decide, each turn, whether to discuss, propose a task, claim
one, or update progress — standing in for a teammate whose own agent isn't
installed on the demo machine.

Usage: python simulate_agent.py --role backend --name "Backend-Agent"
"""
import argparse
import asyncio
import json
import os

from anthropic import Anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:8001/mcp"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM = """You are an AI coding agent representing one member of a small dev \
team. Your assigned role: {role}. You share a workspace with other AI agents \
(possibly running different tools) via a PRD, a discussion thread, and a task \
board. Each turn, look at the PRD, the discussion, and the task board, then \
choose exactly ONE action to move the project forward without duplicating \
work others already claimed. Reply with ONLY a JSON object, one of:
{{"action": "post_message", "text": "..."}}
{{"action": "propose_task", "title": "...", "description": "...", "role": "..."}}
{{"action": "claim_task", "task_id": <int>}}
{{"action": "update_task_status", "task_id": <int>, "status": "in_progress"|"done"}}
{{"action": "noop"}}
Prefer claiming an open task matching your role over proposing a new one if \
one already exists. Keep messages short."""


async def call(session: ClientSession, name: str, **kwargs) -> dict:
    result = await session.call_tool(name, kwargs)
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def decide(client: Anthropic, role: str, prd: str, tasks: list, messages: list) -> dict:
    context = (
        f"PRD:\n{prd}\n\nTasks:\n{json.dumps(tasks, indent=2)}\n\n"
        f"Recent discussion:\n{json.dumps(messages[-10:], indent=2)}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM.format(role=role),
        messages=[{"role": "user", "content": context}],
    )
    text = resp.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"action": "noop"}


async def main(role: str, name: str, turns: int) -> None:
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            joined = await call(session, "register_agent", display_name=name, agent_type="generic")
            agent_id, prd = joined["agent_id"], joined["prd"]
            print(f"[{name}] joined as agent {agent_id}")

            for turn in range(turns):
                tasks = await call(session, "list_tasks")
                messages = await call(session, "list_messages")
                action = await decide(client, role, prd, tasks, messages)
                kind = action.get("action", "noop")
                print(f"[{name}] turn {turn + 1}: {kind}")

                if kind == "post_message":
                    await call(session, "post_message", agent_id=agent_id, text=action["text"])
                elif kind == "propose_task":
                    await call(
                        session, "propose_task", agent_id=agent_id,
                        title=action["title"], description=action.get("description", ""),
                        role=action.get("role", role),
                    )
                elif kind == "claim_task":
                    await call(session, "claim_task", agent_id=agent_id, task_id=action["task_id"])
                elif kind == "update_task_status":
                    await call(
                        session, "update_task_status", agent_id=agent_id,
                        task_id=action["task_id"], status=action["status"],
                    )

                await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--turns", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(main(args.role, args.name or f"{args.role.title()}-Agent", args.turns))
