from lgh.schema.envelope import LayaAction, LayaRepo, LayaState
from lgh.state.budget import HARD_MAX_TOKENS, compress_state, state_token_count
from lgh.state.redact import is_sensitive_target, redact_text


def test_redact_key() -> None:
    text = "Authorization: Bearer abcdefghijklmnop and sk-abcdefghijklmnopqrstuvwxyz"
    out = redact_text(text) or ""
    assert "Bearer abcdef" not in out
    assert "[REDACTED]" in out


def test_sensitive_target() -> None:
    assert is_sensitive_target(".env")
    assert is_sensitive_target("foo.pem")
    assert not is_sensitive_target("src/app.ts")


def test_budget_compresses() -> None:
    state = LayaState(
        goal="x" * 8000,
        plan="y" * 8000,
        repo=LayaRepo(branch="main", dirty=True, changed=[f"f{i}.ts" for i in range(80)]),
        environment="development",
        action=LayaAction(tool="shell", operation="execute", command="z" * 4000),
        recent=[f"edited file {i}" for i in range(20)],
    )
    compressed = compress_state(state)
    assert state_token_count(compressed) <= HARD_MAX_TOKENS
    assert len(compressed.recent) <= 5
    assert len(compressed.repo.changed) <= 20
