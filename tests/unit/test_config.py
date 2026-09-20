from lgh.config.merge import merge_configs
from lgh.config.models import GuardrailConfig
from lgh.schema.decision import Mode


def test_repo_cannot_relax_mode() -> None:
    user = GuardrailConfig(mode=Mode.ENFORCE)
    repo = GuardrailConfig(mode=Mode.SHADOW)
    merged = merge_configs(user, repo)
    assert merged.mode == Mode.ENFORCE


def test_thresholds_tighten() -> None:
    user = GuardrailConfig()
    repo = GuardrailConfig()
    repo.laya.thresholds.destructive = 0.95
    repo.laya.thresholds.confidence = 0.5
    user.laya.thresholds.destructive = 0.85
    user.laya.thresholds.confidence = 0.8
    merged = merge_configs(user, repo)
    assert merged.laya.thresholds.destructive == 0.85
    assert merged.laya.thresholds.confidence == 0.8


def test_protected_union() -> None:
    user = GuardrailConfig(protected_branches=["main"])
    repo = GuardrailConfig(protected_branches=["release"])
    merged = merge_configs(user, repo)
    assert "main" in merged.protected_branches
    assert "release" in merged.protected_branches
