from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    prd_text: str
    created_at: datetime = Field(default_factory=now)


class Agent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id")
    display_name: str
    agent_type: str  # claude_code | codex | antigravity | generic
    status: str = "online"  # online | offline
    connected_at: datetime = Field(default_factory=now)
    last_seen: datetime = Field(default_factory=now)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id")
    title: str
    description: str = ""
    role: str = "general"  # backend | frontend | testing | devops | general
    status: str = "open"  # open | claimed | in_progress | done
    owner_agent_id: Optional[int] = Field(default=None, foreign_key="agent.id")
    created_by: Optional[int] = Field(default=None, foreign_key="agent.id")
    created_at: datetime = Field(default_factory=now)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id")
    agent_id: Optional[int] = Field(default=None, foreign_key="agent.id")  # None = system
    body: str
    created_at: datetime = Field(default_factory=now)
