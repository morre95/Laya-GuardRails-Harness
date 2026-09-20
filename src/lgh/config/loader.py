from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lgh.config.merge import merge_configs
from lgh.config.models import GuardrailConfig
from lgh.paths import repo_config_dir, user_config_path, user_rules_path


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _config_from_mapping(data: dict[str, Any], extra_rules: list[dict] | None = None) -> GuardrailConfig:
    payload = dict(data)
    payload.pop("rules", None)
    cfg = GuardrailConfig.model_validate(payload)
    if extra_rules:
        cfg.extra_repo_rules = extra_rules
    return cfg


def _rules_from_files(*paths: Path) -> list[dict]:
    rules: list[dict] = []
    for path in paths:
        data = _load_yaml(path)
        raw = data.get("rules", [])
        if isinstance(raw, list):
            rules.extend(item for item in raw if isinstance(item, dict))
    return rules


def load_config(
    *,
    cwd: str | Path | None = None,
    repo_root: str | Path | None = None,
    user_config: Path | None = None,
) -> GuardrailConfig:
    user_path = user_config or user_config_path()
    user_data = _load_yaml(user_path)
    user_rules = _rules_from_files(user_rules_path(), user_path)
    user_cfg = _config_from_mapping(user_data)
    user_cfg.extra_user_rules = user_rules

    root = Path(repo_root) if repo_root else (Path(cwd).resolve() if cwd else None)
    if root is None:
        return user_cfg

    guard_dir = repo_config_dir(root)
    assert guard_dir is not None
    repo_data = _load_yaml(guard_dir / "config.yaml")
    repo_rules = _rules_from_files(guard_dir / "rules.yaml", guard_dir / "config.yaml")
    repo_cfg = _config_from_mapping(repo_data, extra_rules=repo_rules)
    merged = merge_configs(user_cfg, repo_cfg)
    merged.extra_user_rules = user_rules
    merged.extra_repo_rules = repo_rules
    return merged
