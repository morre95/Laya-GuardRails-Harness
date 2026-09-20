from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lgh.ids import new_id, utc_now_iso
from lgh.schema.decision import GuardrailDecision
from lgh.schema.envelope import (
    Action,
    ActionEnvelope,
    Context,
    Environment,
    Event,
    Repo,
    Session,
    Task,
)


class FixtureCase(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    goal: str = ""
    action: str = ""
    tool: str = "shell"
    operation: str = "execute"
    target: str | None = None
    command: str | None = None
    environment: str = "development"
    branch: str | None = "feature/test"
    dirty: bool = True
    changed_files: list[str] = Field(default_factory=list)
    acceptable_decisions: list[str] = Field(alias="acceptableDecisions", default_factory=list)
    forbidden_decisions: list[str] = Field(alias="forbiddenDecisions", default_factory=list)
    laya_mock: dict[str, Any] | None = Field(default=None, alias="layaMock")
    category: str = "deterministic"


def load_fixture_files(root: Path) -> list[FixtureCase]:
    cases: list[FixtureCase] = []
    for path in sorted(root.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        category = path.parent.name
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if isinstance(item, dict):
                item.setdefault("category", category)
                cases.append(FixtureCase.model_validate(item))
    return cases


def envelope_from_fixture(case: FixtureCase) -> ActionEnvelope:
    command = case.command if case.command is not None else (case.action or None)
    target = case.target
    return ActionEnvelope(
        schemaVersion="0.1",
        event=Event(id=new_id(), timestamp=utc_now_iso(), phase="PRE_ACTION"),
        session=Session(id="fixture", harness="claude-code"),
        task=Task(userGoal=case.goal, currentPlan=None),
        repo=Repo(
            cwd="/tmp/lgh-fixture",
            root="/tmp/lgh-fixture",
            branch=case.branch,
            dirty=case.dirty,
            changedFiles=case.changed_files,
        ),
        environment=Environment(name=case.environment, confidence=0.8),  # type: ignore[arg-type]
        action=Action(
            tool=case.tool,  # type: ignore[arg-type]
            operation=case.operation,
            target=target,
            command=command,
        ),
        context=Context(activeSkills=[], recentActions=[]),
    )


def forbidden(case: FixtureCase) -> set[GuardrailDecision]:
    return {GuardrailDecision(item) for item in case.forbidden_decisions}


def acceptable(case: FixtureCase) -> set[GuardrailDecision]:
    return {GuardrailDecision(item) for item in case.acceptable_decisions}
