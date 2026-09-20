from __future__ import annotations

from lgh.schema.envelope import ActionEnvelope
from lgh.schema.laya import LayaAssessment
from lgh.schema.verification import VerificationDirective

SKILLS: dict[str, list[str]] = {
    "database-safety": [
        "identify target environment",
        "inspect generated migration",
        "perform dry-run when available",
        "establish rollback strategy",
    ],
    "dependency-review": [
        "identify added or updated packages",
        "check maintainer and license",
        "review changelog for the new versions",
        "run lockfile integrity checks",
    ],
    "security-review": [
        "identify auth and secret touchpoints",
        "check for credential leakage",
        "review authorization changes",
        "confirm tests cover the security path",
    ],
    "plan-first": [
        "summarize the intended file set",
        "split the change into reviewable steps",
        "confirm the user goal still matches",
        "avoid unrelated refactors",
    ],
    "deployment-safety": [
        "identify target environment",
        "confirm this is not a production deploy unless requested",
        "check rollback path",
        "verify health checks after deploy",
    ],
    "generic-verification": [
        "re-read the proposed command and target",
        "confirm it is required for the user goal",
        "state residual risk in one sentence",
        "only then retry the action",
    ],
}

_DB_HINTS = (
    "psql",
    "mysql",
    "mongosh",
    "redis-cli",
    "sqlite",
    "alembic",
    "prisma",
    "knex",
    "db:reset",
    "db:drop",
    "db:push",
    "migrate",
    "drop table",
    "drop database",
)
_DEP_HINTS = (
    "npm install",
    "pnpm add",
    "yarn add",
    "pip install",
    "uv add",
    "poetry add",
    "cargo add",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
)
_SEC_HINTS = (
    "auth",
    "oauth",
    "jwt",
    "rbac",
    "secret",
    "credential",
    ".pem",
    "password",
    "session",
)
_DEPLOY_HINTS = (
    "kubectl",
    "helm",
    "terraform apply",
    "docker push",
    "fly deploy",
    "vercel --prod",
    "gh release",
    "ansible",
    "kubectl apply",
)


def _blob(envelope: ActionEnvelope) -> str:
    action = envelope.action
    return " ".join(
        part
        for part in [action.tool, action.operation, action.target or "", action.command or ""]
        if part
    ).lower()


def select_skill(envelope: ActionEnvelope, assessment: LayaAssessment | None = None) -> str:
    blob = _blob(envelope)
    changed = envelope.repo.changed_files
    if envelope.action.tool == "database" or any(h in blob for h in _DB_HINTS):
        return "database-safety"
    if any(h in blob for h in _DEP_HINTS) or any(
        name in (envelope.action.target or "")
        for name in ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod")
    ):
        return "dependency-review"
    if any(h in blob for h in _SEC_HINTS) or any(
        h in (envelope.action.target or "").lower() for h in _SEC_HINTS
    ):
        return "security-review"
    if len(changed) > 15:
        return "plan-first"
    if any(h in blob for h in _DEPLOY_HINTS):
        return "deployment-safety"
    if assessment and assessment.sensitive_resource >= 0.7:
        return "security-review"
    return "generic-verification"


def route_verification(
    envelope: ActionEnvelope, assessment: LayaAssessment | None = None
) -> VerificationDirective:
    skill = select_skill(envelope, assessment)
    return VerificationDirective(
        skill=skill,
        requirements=list(SKILLS[skill]),
        resumePolicy="REEVALUATE_ACTION",
    )
