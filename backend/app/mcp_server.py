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

from .db import get_session, init_db
from .models import Agent, Message, Task, Workspace

mcp = FastMCP("agent-collab-platform", host="0.0.0.0", port=8001, streamable_http_path="/mcp")


def _active_workspace(session) -> Workspace:
    ws = session.exec(select(Workspace).order_by(Workspace.id.desc())).first()
    if not ws:
        raise ValueError("No workspace yet — run seed_demo.py first")
    return ws


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
        return {"agent_id": agent.id, "workspace_name": ws.name, "prd": ws.prd_text}


@mcp.tool()
def get_prd() -> str:
    """Read the shared goal / Product Requirements Document for the active workspace."""
    with get_session() as session:
        return _active_workspace(session).prd_text


@mcp.tool()
def list_tasks() -> list[dict]:
    """List every task on the shared board with its status and owner."""
    with get_session() as session:
        ws = _active_workspace(session)
        tasks = session.exec(select(Task).where(Task.workspace_id == ws.id)).all()
        return [t.model_dump() for t in tasks]


@mcp.tool()
def list_messages(limit: int = 50) -> list[dict]:
    """Read the recent discussion thread — use this to see what other agents
    have proposed before you propose or claim anything."""
    with get_session() as session:
        ws = _active_workspace(session)
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
        session.add(Message(workspace_id=ws.id, agent_id=agent_id, body=text))
        session.commit()
        return {"ok": True}


@mcp.tool()
def propose_task(agent_id: int, title: str, description: str = "", role: str = "general") -> dict:
    """Add a task to the shared board (e.g. after negotiating a split in the
    discussion thread)."""
    with get_session() as session:
        ws = _active_workspace(session)
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
        task = session.get(Task, task_id)
        if not task:
            return {"ok": False, "error": "no such task"}
        if task.owner_agent_id != agent_id:
            return {"ok": False, "error": "you do not own this task"}
        task.status = status
        session.add(task)
        session.commit()
        return {"ok": True}


if __name__ == "__main__":
    init_db()
    mcp.run(transport="streamable-http")
