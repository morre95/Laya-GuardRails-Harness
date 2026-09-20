from typing import Any, Literal

from pydantic import Field

from lgh.schema.base import FrozenModel

SchemaVersion = Literal["0.1"]
Phase = Literal["PRE_ACTION", "POST_ACTION", "STOP"]
HarnessName = Literal["claude-code", "codex", "unknown"]
EnvironmentName = Literal[
    "local",
    "development",
    "test",
    "staging",
    "production",
    "unknown",
]
ToolName = Literal[
    "shell",
    "read",
    "write",
    "edit",
    "network",
    "git",
    "database",
    "mcp",
    "unknown",
]


class Event(FrozenModel):
    id: str
    timestamp: str
    phase: Phase


class Session(FrozenModel):
    id: str
    harness: HarnessName


class Task(FrozenModel):
    user_goal: str = Field(alias="userGoal")
    current_plan: str | None = Field(default=None, alias="currentPlan")


class Repo(FrozenModel):
    cwd: str
    root: str | None = None
    branch: str | None = None
    dirty: bool
    changed_files: list[str] = Field(alias="changedFiles")


class Environment(FrozenModel):
    name: EnvironmentName
    confidence: float


class Action(FrozenModel):
    tool: ToolName
    operation: str
    target: str | None = None
    command: str | None = None
    arguments: Any | None = None


class ActionSummary(FrozenModel):
    tool: str
    operation: str
    target: str | None = None
    command: str | None = None
    summary: str


class Context(FrozenModel):
    active_skills: list[str] = Field(alias="activeSkills")
    recent_actions: list[ActionSummary] = Field(alias="recentActions")


class ActionEnvelope(FrozenModel):
    schema_version: SchemaVersion = Field(alias="schemaVersion")
    event: Event
    session: Session
    task: Task
    repo: Repo
    environment: Environment
    action: Action
    context: Context


class LayaAction(FrozenModel):
    tool: str
    operation: str
    command: str | None = None
    target: str | None = None


class LayaRepo(FrozenModel):
    branch: str | None = None
    dirty: bool = False
    changed: list[str] = Field(default_factory=list)


class LayaState(FrozenModel):
    """Compact state for Laya. Target ≤500 tokens, hard max 700."""

    goal: str
    plan: str | None = None
    repo: LayaRepo
    environment: EnvironmentName
    action: LayaAction
    recent: list[str] = Field(default_factory=list)
