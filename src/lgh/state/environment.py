from __future__ import annotations

import os
import re
from pathlib import Path

from lgh.config.models import GuardrailConfig
from lgh.schema.envelope import Action, Environment

_PROD_FLAG = re.compile(r"(?i)(?:^|[\s=])(--prod(?:uction)?|NODE_ENV=production|ENV=production)(?:\s|$)")
_PROD_HOST = re.compile(r"(?i)\b(?:prod|production|live)\b[.-][a-z0-9.-]+")


def detect_environment(
    *,
    branch: str | None,
    command: str | None,
    cwd: str,
    config: GuardrailConfig,
    action: Action | None = None,
) -> Environment:
    production_branches = {b.lower() for b in config.environment.production_branches}
    if branch and branch.lower() in production_branches:
        return Environment(name="production", confidence=0.9)

    blob = " ".join(part for part in [command, action.target if action else None] if part)
    if blob and (_PROD_FLAG.search(blob) or _PROD_HOST.search(blob)):
        return Environment(name="production", confidence=0.75)

    env_name = os.environ.get("LGH_ENVIRONMENT")
    if env_name in {"local", "development", "test", "staging", "production", "unknown"}:
        return Environment(name=env_name, confidence=0.85)  # type: ignore[arg-type]

    cwd_path = Path(cwd)
    names = [p.name.lower() for p in cwd_path.glob(".env*")] if cwd_path.is_dir() else []
    joined = " ".join(names)
    if "prod" in joined:
        return Environment(name="production", confidence=0.55)
    if any(p.is_dir() and (p / ".git").exists() for p in [cwd_path, *cwd_path.parents]):
        return Environment(name="development", confidence=0.6)
    return Environment(name="unknown", confidence=0.3)
