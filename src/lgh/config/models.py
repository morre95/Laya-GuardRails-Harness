from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lgh.schema.decision import Mode


class MutableModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class LayaThresholds(MutableModel):
    confidence: float = 0.80
    destructive: float = 0.85
    sensitive: float = 0.85
    external_impact: float = 0.85
    verification: float = 0.70


class LayaConfig(MutableModel):
    model: str = "convaiinnovations/laya-typed-decisions"
    daemon_url: str = "http://127.0.0.1:8765"
    timeout_seconds: float = 3.0
    device: str = "cpu"
    thresholds: LayaThresholds = Field(default_factory=LayaThresholds)
    temperatures: dict[str, float] = Field(default_factory=dict)


class EnvironmentConfig(MutableModel):
    production_branches: list[str] = Field(default_factory=lambda: ["main", "production"])


class ReviewConfig(MutableModel):
    frontier_enabled: bool = True
    timeout_seconds: float = 20.0
    model: str = "claude"
    # Calling `claude -p` from inside a hook costs seconds. In shadow mode the
    # result cannot change behaviour, so skip it by default and leave the
    # policy decision as FRONTIER_REVIEW in the trace.
    run_in_shadow: bool = False


class TeacherConfig(MutableModel):
    """Labeling teacher for `lgh review --propose`. User config only."""

    provider: str = "openrouter"
    model: str = ""
    base_url: str = "https://openrouter.ai/api/v1"


class HumanConfig(MutableModel):
    production_mutations: str = "always"


class GuardrailConfig(MutableModel):
    version: str = "0.1"
    mode: Mode = Mode.SHADOW
    allow_passthrough: bool = False
    enforce_categories: list[str] = Field(default_factory=list)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    protected_paths: list[str] = Field(
        default_factory=lambda: [".github/**", "infra/**", "migrations/**"]
    )
    protected_branches: list[str] = Field(default_factory=lambda: ["main", "production"])
    laya: LayaConfig = Field(default_factory=LayaConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    teacher: TeacherConfig = Field(default_factory=TeacherConfig)
    human: HumanConfig = Field(default_factory=HumanConfig)
    delete_threshold: int = 50
    require_tests: bool = False
    known_test_commands: list[str] = Field(
        default_factory=lambda: [
            "pytest",
            "python -m pytest",
            "npm test",
            "npm run test",
            "pnpm test",
            "cargo test",
            "go test",
            "make test",
            "uv run pytest",
        ]
    )
    known_lint_commands: list[str] = Field(
        default_factory=lambda: [
            "ruff",
            "ruff check",
            "eslint",
            "npm run lint",
            "pnpm lint",
            "cargo clippy",
        ]
    )
    known_typecheck_commands: list[str] = Field(
        default_factory=lambda: [
            "mypy",
            "pyright",
            "tsc",
            "npm run typecheck",
            "npx tsc",
            "cargo check",
        ]
    )
    max_verification_cycles: int = 2
    max_replans_per_action: int = 2
    hook_timeout_seconds: int = 30
    extra_repo_rules: list[dict] = Field(default_factory=list)
    extra_user_rules: list[dict] = Field(default_factory=list)
