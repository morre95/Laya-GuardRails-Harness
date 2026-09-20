from __future__ import annotations

from lgh.config.models import GuardrailConfig
from lgh.schema.envelope import ActionEnvelope
from lgh.adapters.claude_code.repo import inspect_repo


def stop_issues(envelope: ActionEnvelope, session: dict, config: GuardrailConfig) -> list[str]:
    issues: list[str] = []
    _root, _branch, dirty, changed = inspect_repo(envelope.repo.cwd)
    known = set(session.get("changed_files") or [])
    unexpected = [path for path in changed if path not in known]
    if dirty and unexpected:
        issues.append("uncommitted unexpected changes: " + ", ".join(unexpected[:8]))
    tests_mentioned = config.require_tests or "test" in envelope.task.user_goal.lower()
    executed = session.get("executed_tests") or []
    if tests_mentioned and not executed:
        issues.append("tests requested but not run")
    last_exit = session.get("last_test_exit")
    if last_exit not in {None, 0}:
        issues.append(f"failed tests (exit {last_exit})")
    if session.get("pending_verification"):
        issues.append("unfinished verification")
    pending_human = session.get("pending_human")
    if isinstance(pending_human, dict) and pending_human.get("requested") and not pending_human.get("decision"):
        issues.append("pending human decision")
    if session.get("block_violations"):
        issues.append("guardrail violations in session")
    return issues
