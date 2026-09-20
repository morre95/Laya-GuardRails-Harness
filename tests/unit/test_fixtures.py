from pathlib import Path

from lgh.config.models import GuardrailConfig
from lgh.eval.runner import run_fixtures
from lgh.schema.decision import Mode


def test_fixtures_forbid_false_allows(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    summary = run_fixtures(
        root,
        config=GuardrailConfig(mode=Mode.ENFORCE),
        traces_dir=tmp_path / "t",
        sessions_dir=tmp_path / "s",
    )
    assert summary["n"] >= 100
    assert summary["false_allow_rate"] == 0
    assert summary["forbidden_hits"] == 0, summary["failures"][:10]
