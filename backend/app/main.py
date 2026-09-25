"""Dashboard API for the human-visible side of the platform: read-only REST
endpoints plus an SSE stream that polls the shared SQLite DB (also written to
by mcp_server.py) so the frontend updates live as agents act."""
import asyncio
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from sqlmodel import select

from . import repo
from .db import get_session, init_db
from .models import Agent, Message, Task, Workspace

app = FastAPI(title="Agent Collab Platform")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# An agent that hasn't called any MCP tool in this long is shown offline —
# distinguishes a live teammate from one whose process already exited.
ONLINE_THRESHOLD_SECONDS = 20


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _agent_dict(a: Agent) -> dict:
    d = a.model_dump(mode="json")
    last_seen = a.last_seen if a.last_seen.tzinfo else a.last_seen.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    d["status"] = "online" if age < ONLINE_THRESHOLD_SECONDS else "offline"
    return d


def _snapshot() -> dict:
    with get_session() as session:
        ws = session.exec(select(Workspace).order_by(Workspace.id.desc())).first()
        if not ws:
            return {"workspace": None, "agents": [], "tasks": [], "messages": []}
        agents = session.exec(select(Agent).where(Agent.workspace_id == ws.id)).all()
        tasks = session.exec(select(Task).where(Task.workspace_id == ws.id)).all()
        msgs = session.exec(
            select(Message).where(Message.workspace_id == ws.id).order_by(Message.id)
        ).all()
        return {
            "workspace": ws.model_dump(mode="json"),
            "agents": [_agent_dict(a) for a in agents],
            "tasks": [t.model_dump(mode="json") for t in tasks],
            "messages": [m.model_dump(mode="json") for m in msgs],
            "repo": {"files": repo.list_files(), "commits": repo.log(20)},
        }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/state")
def state() -> dict:
    return _snapshot()


@app.get("/api/repo/file")
def repo_file(path: str) -> dict:
    try:
        return {"path": path, "content": repo.read_file(path)}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/stream")
async def stream():
    async def gen():
        last = None
        while True:
            snap = _snapshot()
            payload = json.dumps(snap, default=str)
            if payload != last:
                yield {"event": "state", "data": payload}
                last = payload
            await asyncio.sleep(1)

    return EventSourceResponse(gen())
