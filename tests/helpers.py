from lgh.ids import new_id, utc_now_iso
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


def make_envelope(**kwargs) -> ActionEnvelope:
    action_kw = kwargs.pop("action_kw", {})
    return ActionEnvelope(
        schemaVersion="0.1",
        event=Event(id=new_id(), timestamp=utc_now_iso(), phase="PRE_ACTION"),
        session=Session(id=kwargs.get("session_id", "s1"), harness="claude-code"),
        task=Task(userGoal=kwargs.get("goal", "Do a thing"), currentPlan=kwargs.get("plan")),
        repo=Repo(
            cwd=kwargs.get("cwd", "/tmp/lgh-fixture"),
            root=kwargs.get("root", "/tmp/lgh-fixture"),
            branch=kwargs.get("branch", "feature/x"),
            dirty=kwargs.get("dirty", True),
            changedFiles=kwargs.get("changed", ["src/a.ts"]),
        ),
        environment=Environment(
            name=kwargs.get("environment", "development"),
            confidence=kwargs.get("env_confidence", 0.7),
        ),
        action=Action(
            tool=kwargs.get("tool", "shell"),
            operation=kwargs.get("operation", "execute"),
            target=kwargs.get("target"),
            command=kwargs.get("command"),
            arguments=action_kw or None,
        ),
        context=Context(activeSkills=[], recentActions=[]),
    )
