from __future__ import annotations

from lgh.config.models import GuardrailConfig, LayaThresholds
from lgh.schema.decision import MODE_RANK, Mode
from lgh.schema.rules import DISPOSITION_RANK, RuleDisposition


def _union(a: list[str], b: list[str]) -> list[str]:
    seen: list[str] = []
    for item in [*a, *b]:
        if item not in seen:
            seen.append(item)
    return seen


def _stricter_mode(user: Mode, repo: Mode) -> Mode:
    return user if MODE_RANK[user] >= MODE_RANK[repo] else repo


def _stricter_thresholds(user: LayaThresholds, repo: LayaThresholds) -> LayaThresholds:
    return LayaThresholds(
        confidence=max(user.confidence, repo.confidence),
        destructive=min(user.destructive, repo.destructive),
        sensitive=min(user.sensitive, repo.sensitive),
        external_impact=min(user.external_impact, repo.external_impact),
        verification=min(user.verification, repo.verification),
    )


def merge_configs(user: GuardrailConfig, repo: GuardrailConfig) -> GuardrailConfig:
    """Repo policy may only tighten user/global policy."""
    merged = user.model_copy(deep=True)
    merged.mode = _stricter_mode(user.mode, repo.mode)
    merged.allow_passthrough = user.allow_passthrough and repo.allow_passthrough
    merged.enforce_categories = _union(user.enforce_categories, repo.enforce_categories)
    merged.environment.production_branches = _union(
        user.environment.production_branches,
        repo.environment.production_branches,
    )
    merged.protected_paths = _union(user.protected_paths, repo.protected_paths)
    merged.protected_branches = _union(user.protected_branches, repo.protected_branches)
    merged.laya.thresholds = _stricter_thresholds(user.laya.thresholds, repo.laya.thresholds)
    if repo.laya.model:
        merged.laya.model = repo.laya.model
    merged.laya.temperatures = {**repo.laya.temperatures, **user.laya.temperatures}
    merged.review.frontier_enabled = user.review.frontier_enabled or repo.review.frontier_enabled
    if user.human.production_mutations == "always" or repo.human.production_mutations == "always":
        merged.human.production_mutations = "always"
    merged.delete_threshold = min(user.delete_threshold, repo.delete_threshold)
    merged.require_tests = user.require_tests or repo.require_tests
    merged.known_test_commands = _union(user.known_test_commands, repo.known_test_commands)
    merged.known_lint_commands = _union(user.known_lint_commands, repo.known_lint_commands)
    merged.known_typecheck_commands = _union(
        user.known_typecheck_commands, repo.known_typecheck_commands
    )
    merged.max_verification_cycles = min(
        user.max_verification_cycles, repo.max_verification_cycles
    )
    merged.max_replans_per_action = min(user.max_replans_per_action, repo.max_replans_per_action)
    merged.extra_repo_rules = list(repo.extra_repo_rules)
    merged.extra_user_rules = list(user.extra_user_rules)
    return merged


def stricter_disposition(a: RuleDisposition, b: RuleDisposition) -> RuleDisposition:
    return a if DISPOSITION_RANK[a] >= DISPOSITION_RANK[b] else b
