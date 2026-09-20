from lgh.config.models import GuardrailConfig
from lgh.stopguard.checks import stop_issues
from lgh.verification.router import select_skill
from tests.helpers import make_envelope


def test_database_skill() -> None:
    env = make_envelope(command="npm run db:reset")
    assert select_skill(env) == "database-safety"


def test_stop_issues_pending_human() -> None:
    env = make_envelope(goal="add tests for parser")
    issues = stop_issues(
        env,
        {"pending_human": {"requested": True}, "executed_tests": [], "changed_files": []},
        GuardrailConfig(require_tests=True),
    )
    assert any("human" in i for i in issues)
    assert any("tests requested" in i for i in issues)
