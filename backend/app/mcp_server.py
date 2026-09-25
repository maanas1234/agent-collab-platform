"""MCP server: the surface any AI coding agent (Claude Code, Codex, Antigravity,
or a plain script) connects to as an MCP client to join a workspace, read the
PRD, discuss, and claim/execute tasks.

Run standalone: python -m app.mcp_server   (serves streamable-http on :8001)
Point a real agent at it, e.g.:
  claude mcp add --transport http agent-platform http://localhost:8001/mcp
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP
from sqlmodel import select

from . import repo
from .db import get_session, init_db
from .models import Agent, Message, Task, Workspace, now

mcp = FastMCP("agent-collab-platform", host="0.0.0.0", port=8001, streamable_http_path="/mcp")


def _active_workspace(session) -> Workspace:
    ws = session.exec(select(Workspace).order_by(Workspace.id.desc())).first()
    if not ws:
        raise ValueError("No workspace yet — run seed_demo.py first")
    return ws


def _touch(session, agent_id: Optional[int]) -> None:
    """Record that an agent is still active — drives the online/offline dot
    on the dashboard (see main.py's ONLINE_THRESHOLD_SECONDS)."""
    if agent_id is None:
        return
    agent = session.get(Agent, agent_id)
    if agent:
        agent.last_seen = now()
        session.add(agent)
        session.commit()


@mcp.tool()
def register_agent(display_name: str, agent_type: str = "generic") -> dict:
    """Join the active workspace as a participant. Call this first — every
    other tool needs the agent_id it returns."""
    with get_session() as session:
        ws = _active_workspace(session)
        agent = Agent(workspace_id=ws.id, display_name=display_name, agent_type=agent_type)
        session.add(agent)
        session.commit()
        session.refresh(agent)
        session.add(Message(workspace_id=ws.id, agent_id=None, body=f"{display_name} ({agent_type}) joined the workspace."))
        session.commit()
        return {"agent_id": agent.id, "workspace_name": ws.name, "prd": ws.prd_text, "started": ws.started}


@mcp.tool()
def get_prd() -> str:
    """Read the shared goal / Product Requirements Document for the active workspace."""
    with get_session() as session:
        return _active_workspace(session).prd_text


@mcp.tool()
def is_started(agent_id: Optional[int] = None) -> bool:
    """Check whether a human has started the workspace yet. Agents should
    register, then poll this and wait (don't propose/claim/write anything)
    until it returns true — connecting isn't the same as being told to go."""
    with get_session() as session:
        _touch(session, agent_id)
        return _active_workspace(session).started


@mcp.tool()
def list_tasks(agent_id: Optional[int] = None) -> list[dict]:
    """List every task on the shared board with its status and owner."""
    with get_session() as session:
        ws = _active_workspace(session)
        _touch(session, agent_id)
        tasks = session.exec(select(Task).where(Task.workspace_id == ws.id)).all()
        return [t.model_dump() for t in tasks]


@mcp.tool()
def list_messages(limit: int = 50, agent_id: Optional[int] = None) -> list[dict]:
    """Read the recent discussion thread — use this to see what other agents
    have proposed before you propose or claim anything."""
    with get_session() as session:
        ws = _active_workspace(session)
        _touch(session, agent_id)
        msgs = session.exec(
            select(Message).where(Message.workspace_id == ws.id).order_by(Message.id.desc()).limit(limit)
        ).all()
        return [m.model_dump() for m in reversed(msgs)]


@mcp.tool()
def post_message(agent_id: int, text: str) -> dict:
    """Post to the shared discussion thread — propose a plan, ask a question,
    or announce what you're doing."""
    with get_session() as session:
        ws = _active_workspace(session)
        _touch(session, agent_id)
        session.add(Message(workspace_id=ws.id, agent_id=agent_id, body=text))
        session.commit()
        return {"ok": True}


@mcp.tool()
def propose_task(agent_id: int, title: str, description: str = "", role: str = "general") -> dict:
    """Add a task to the shared board (e.g. after negotiating a split in the
    discussion thread)."""
    with get_session() as session:
        ws = _active_workspace(session)
        _touch(session, agent_id)
        task = Task(workspace_id=ws.id, title=title, description=description, role=role, created_by=agent_id)
        session.add(task)
        session.commit()
        session.refresh(task)
        return {"task_id": task.id}


@mcp.tool()
def claim_task(agent_id: int, task_id: int) -> dict:
    """Claim ownership of an open task. Fails if someone already claimed it —
    check list_tasks() first to avoid duplicate work."""
    with get_session() as session:
        _touch(session, agent_id)
        task = session.get(Task, task_id)
        if not task:
            return {"ok": False, "error": "no such task"}
        if task.status != "open":
            return {"ok": False, "error": f"task already {task.status}"}
        task.status = "claimed"
        task.owner_agent_id = agent_id
        session.add(task)
        session.commit()
        return {"ok": True}


@mcp.tool()
def update_task_status(agent_id: int, task_id: int, status: str) -> dict:
    """Update progress on a task you own. status: in_progress | done."""
    with get_session() as session:
        _touch(session, agent_id)
        task = session.get(Task, task_id)
        if not task:
            return {"ok": False, "error": "no such task"}
        if task.owner_agent_id != agent_id:
            return {"ok": False, "error": "you do not own this task"}
        task.status = status
        session.add(task)
        session.commit()
        return {"ok": True}


@mcp.tool()
def write_file(agent_id: int, task_id: int, path: str, content: str, message: str = "") -> dict:
    """Write a file into the shared project repo and commit it under your
    name — this is the actual codebase the team is building, separate from
    the task board. Fails if you don't own task_id, so ownership and code
    stay tied together. Use list_repo_files/read_repo_file first to see
    what teammates already wrote before you add or change something."""
    with get_session() as session:
        _touch(session, agent_id)
        agent = session.get(Agent, agent_id)
        task = session.get(Task, task_id)
        if not agent:
            return {"ok": False, "error": "no such agent"}
        if not task:
            return {"ok": False, "error": "no such task"}
        if task.owner_agent_id != agent_id:
            return {"ok": False, "error": "you do not own this task"}
        try:
            commit_msg = message or f"{path}: {task.title}"
            commit_hash = repo.write_and_commit(path, content, agent.display_name, commit_msg)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        session.add(Message(
            workspace_id=task.workspace_id, agent_id=agent_id,
            body=f"committed {path} ({commit_hash}) for task #{task_id}: {commit_msg}",
        ))
        session.commit()
        return {"ok": True, "commit": commit_hash}


@mcp.tool()
def list_repo_files(agent_id: Optional[int] = None) -> list[str]:
    """List every file currently in the shared project repo."""
    with get_session() as session:
        _touch(session, agent_id)
    return repo.list_files()


@mcp.tool()
def read_repo_file(path: str, agent_id: Optional[int] = None) -> str:
    """Read a file from the shared project repo — check what a teammate
    already built before writing something that conflicts with it."""
    with get_session() as session:
        _touch(session, agent_id)
    try:
        return repo.read_file(path)
    except FileNotFoundError:
        return f"(no such file: {path})"


@mcp.tool()
def repo_log(limit: int = 20, agent_id: Optional[int] = None) -> list[dict]:
    """List recent commits to the shared project repo — who wrote what, in order."""
    with get_session() as session:
        _touch(session, agent_id)
    return repo.log(limit)


if __name__ == "__main__":
    init_db()
    repo.ensure_repo()
    mcp.run(transport="streamable-http")
