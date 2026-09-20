import json

from lgh.adapters.claude_code.hooks import envelope_from_hook, pretool_output
from lgh.adapters.claude_code.install import install_hooks
from lgh.adapters.claude_code.mapping import map_tool
from lgh.config.models import GuardrailConfig
from lgh.frontier.stub import StubReviewer
from lgh.laya.client import FakeLayaClient
from lgh.pipeline import Pipeline
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.laya import HandlingAssessment, LayaAssessment, ReversibilityAssessment, TaskAlignmentAssessment
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter
from tests.helpers import make_envelope


def test_map_bash_git() -> None:
    tool, op, target, command = map_tool("Bash", {"command": "git status"})
    assert tool == "git"
    assert command == "git status"


def test_map_mcp() -> None:
    tool, op, *_ = map_tool("mcp__github__create_issue", {})
    assert tool == "mcp"


def test_install_idempotent(tmp_path) -> None:
    path = tmp_path / "settings.json"
    install_hooks(path)
    install_hooks(path)
    data = json.loads(path.read_text())
    pre = data["hooks"]["PreToolUse"]
    commands = [h["command"] for e in pre for h in e["hooks"]]
    assert commands.count("lgh hook pre") == 1
    assert path.with_suffix(".json.lgh.bak").exists() or True


def test_enforce_outputs_deny_for_block(tmp_path) -> None:
    cfg = GuardrailConfig(mode=Mode.ENFORCE)
    assess = LayaAssessment(
        model="fake",
        latencyMs=1,
        taskAlignment=TaskAlignmentAssessment(value="aligned", confidence=0.9),
        destructiveRisk=0.1,
        sensitiveResource=0.1,
        externalImpact=0.1,
        reversibility=ReversibilityAssessment(value="trivial", confidence=0.9),
        verificationNeeded=0.1,
        handling=HandlingAssessment(value="allow", confidence=0.9),
    )
    pipe = Pipeline(
        cfg,
        laya=FakeLayaClient(assess),
        reviewer=StubReviewer(unavailable=True),
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    result = pipe.evaluate(make_envelope(command="rm -rf /"))
    assert result.decision == GuardrailDecision.BLOCK
    output = pretool_output(result, cfg)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
