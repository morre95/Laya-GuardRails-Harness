from __future__ import annotations

import fnmatch
from functools import lru_cache
from typing import Any, Callable

import yaml

from lgh.config.merge import stricter_disposition
from lgh.config.models import GuardrailConfig
from lgh.resources import read_package_text
from lgh.rules.shell import (
    GIT_READONLY,
    ParsedCommand,
    is_outside_repo,
    looks_like_home_delete,
    looks_like_root_delete,
    parse_command,
    resolve_path,
)
from lgh.schema.envelope import ActionEnvelope
from lgh.schema.rules import DISPOSITION_RANK, RuleDisposition, RuleMatch, RuleResult

Evaluator = Callable[[ActionEnvelope, GuardrailConfig, dict[str, Any], list[ParsedCommand]], bool]

_ENV_GLOBS = [".env", ".env.*", "**/.env", "**/.env.*", "**/.env.local", "**/.env.production"]
_PEM_GLOBS = ["*.pem", "**/*.pem", "*.key", "**/*.key"]
_SECRET_READ_GLOBS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/*.pem",
    "**/id_rsa",
    "**/id_ed25519",
    "**/credentials.json",
    "**/.docker/config.json",
    "**/secrets.yaml",
    "**/secrets.yml",
]
_LGH_RULE_GLOBS = ["**/.guardrail/rules.yaml", ".guardrail/rules.yaml"]
_LGH_CONFIG_GLOBS = [
    "**/.guardrail/config.yaml",
    ".guardrail/config.yaml",
    "**/.config/lgh/config.yaml",
    "**/.config/lgh/rules.yaml",
]
_HOOK_GLOBS = [
    "**/.claude/settings.json",
    "**/.claude/settings.local.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    "**/.claude/hooks/**",
    "**/.config/lgh/**",
    "**/.local/state/lgh/**",
]
_DB_BINS = {"psql", "mysql", "mysqladmin", "mongosh", "mongo", "redis-cli", "sqlite3"}
_DB_PATTERNS = (
    "db:reset",
    "db:drop",
    "db:push",
    "migrate",
    "alembic",
    "prisma migrate",
    "knex migrate",
    "drop table",
    "drop database",
    "truncate ",
)
_MUTATING_TOOLS = {"write", "edit", "shell", "git", "database", "network", "mcp"}
_RISKY_TOOLS = {"write", "edit", "shell", "git", "database", "network", "mcp"}


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _matches_globs(target: str | None, globs: list[str]) -> bool:
    if not target:
        return False
    value = _norm(target)
    name = value.rsplit("/", 1)[-1]
    for glob in globs:
        if fnmatch.fnmatch(value, glob) or fnmatch.fnmatch(name, glob):
            return True
        if glob.startswith("**/") and fnmatch.fnmatch(name, glob[3:]):
            return True
    return False


def _targets(envelope: ActionEnvelope, parsed: list[ParsedCommand]) -> list[str]:
    found: list[str] = []
    if envelope.action.target:
        found.append(envelope.action.target)
    for item in parsed:
        found.extend(item.writes)
        # git add/commit paths ignored
    return found


def _is_write(envelope: ActionEnvelope) -> bool:
    return envelope.action.tool in {"write", "edit"} or envelope.action.operation in {
        "write",
        "edit",
        "create",
        "update",
    }


def _ssh_target(target: str | None) -> bool:
    if not target:
        return False
    value = _norm(target)
    return "/.ssh/" in value or value.startswith("~/.ssh/") or fnmatch.fnmatch(value, "**/id_rsa") or fnmatch.fnmatch(
        value, "**/id_ed25519"
    )


def eval_write_env(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    hits = any(_matches_globs(t, _ENV_GLOBS) for t in _targets(env, parsed))
    return hits and (_is_write(env) or any(item.writes for item in parsed))


def eval_write_pem(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    hits = any(_matches_globs(t, _PEM_GLOBS) for t in _targets(env, parsed))
    return hits and (_is_write(env) or any(item.writes for item in parsed))


def eval_write_ssh(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    hits = any(_ssh_target(t) for t in _targets(env, parsed))
    return hits and (_is_write(env) or any(item.writes for item in parsed))


def eval_read_secrets(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    if env.action.tool != "read":
        # cat .env via shell
        for item in parsed:
            if item.binary in {"cat", "less", "head", "tail", "bat"} and any(
                _matches_globs(a, _SECRET_READ_GLOBS) for a in item.argv[1:]
            ):
                return True
        return False
    return _matches_globs(env.action.target, _SECRET_READ_GLOBS)


def eval_rm_root(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    cmd = env.action.command or ""
    return any(looks_like_root_delete(cmd, item) for item in parsed)


def eval_rm_home(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    cmd = env.action.command or ""
    return any(looks_like_home_delete(cmd, item) for item in parsed)


def eval_rm_outside(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    cwd = env.repo.cwd
    root = env.repo.root
    for item in parsed:
        for target in item.recursive_delete_targets:
            resolved = resolve_path(target, cwd)
            if is_outside_repo(resolved, root, cwd) and target not in {"/", "~", "$HOME"}:
                if looks_like_root_delete(env.action.command or "", item):
                    continue
                if looks_like_home_delete(env.action.command or "", item):
                    continue
                return True
    return False


def eval_delete_threshold(
    env: ActionEnvelope, cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]
) -> bool:
    total = 0
    for item in parsed:
        total += item.file_delete_count
        if item.recursive_delete_targets:
            total = max(total, cfg.delete_threshold + 1)
    return total > cfg.delete_threshold


def _git_items(parsed: list[ParsedCommand], env: ActionEnvelope) -> list[ParsedCommand]:
    items = [p for p in parsed if p.is_git]
    if env.action.tool == "git" and not items:
        fake_cmd = env.action.command or f"git {env.action.operation}"
        items = [p for p in parse_command(fake_cmd) if p.is_git]
    return items


def eval_git_readonly(env: ActionEnvelope, _cfg: GuardrailConfig, rule: dict, parsed: list[ParsedCommand]) -> bool:
    allowed = set(rule.get("git_subcommands") or [])
    items = _git_items(parsed, env)
    if not items:
        return False
    return all((item.git_subcommand or "") in allowed for item in items)


def eval_git_reset_hard(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    return any(
        item.git_subcommand == "reset" and any(f in {"--hard", "-hard"} or f.startswith("--hard") for f in item.git_flags)
        or (item.git_subcommand == "reset" and "--hard" in item.argv)
        for item in _git_items(parsed, env)
    )


def eval_git_clean(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    return any(
        item.git_subcommand == "clean"
        and (
            any(f in {"-fd", "-df", "-f", "-d", "-xfd", "-fdx"} or "f" in f.lstrip("-") for f in item.git_flags)
            or "-fd" in item.raw
            or "-df" in item.raw
        )
        for item in _git_items(parsed, env)
    )


def eval_git_force_push(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    return any(
        item.git_subcommand == "push"
        and any(f in {"--force", "-f", "--force-with-lease"} for f in item.git_flags + tuple(item.argv))
        for item in _git_items(parsed, env)
    )


def eval_git_protected_push(
    env: ActionEnvelope, cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]
) -> bool:
    protected = {b.lower() for b in cfg.protected_branches}
    for item in _git_items(parsed, env):
        if item.git_subcommand != "push":
            continue
        tokens = [t.lower() for t in item.argv if not t.startswith("-")]
        # git push origin main
        if any(tok in protected for tok in tokens[1:]):
            return True
        if env.repo.branch and env.repo.branch.lower() in protected and len(tokens) <= 2:
            return True
    return False


def _command_text(env: ActionEnvelope) -> str:
    return (env.action.command or env.action.operation or "").strip()


def eval_known_command(env: ActionEnvelope, cfg: GuardrailConfig, rule: dict, parsed: list[ParsedCommand]) -> bool:
    kind = rule.get("command_kind")
    catalog = {
        "test": cfg.known_test_commands,
        "lint": cfg.known_lint_commands,
        "typecheck": cfg.known_typecheck_commands,
    }[kind]
    text = _command_text(env)
    if any(text == cmd or text.startswith(cmd + " ") for cmd in catalog):
        return True
    for item in parsed:
        joined = " ".join(item.argv)
        if any(joined == cmd or joined.startswith(cmd + " ") for cmd in catalog):
            return True
    return False


def eval_package_install(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    if any(item.is_package_install for item in parsed):
        return True
    target = env.action.target or ""
    return _is_write(env) and any(
        name in _norm(target)
        for name in ("package.json", "package-lock.json", "pnpm-lock.yaml", "pyproject.toml", "requirements.txt", "Cargo.lock", "go.mod")
    )


def _is_mutating(env: ActionEnvelope, parsed: list[ParsedCommand]) -> bool:
    if env.action.tool in _MUTATING_TOOLS and env.action.tool != "git":
        if env.action.tool == "shell":
            return not eval_known_command(
                env,
                GuardrailConfig(),
                {"command_kind": "test"},
                parsed,
            )
        return True
    if env.action.tool == "git":
        return True
    return any(item.is_git and item.git_subcommand not in {"status", "diff", "log", "show"} for item in parsed)


def eval_production_mutation(
    env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]
) -> bool:
    if env.environment.name != "production":
        return False
    if env.action.tool in {"read"}:
        return False
    git_items = _git_items(parsed, env)
    if git_items and all((item.git_subcommand or "") in GIT_READONLY for item in git_items):
        others = [p for p in parsed if not p.is_git]
        if not others:
            return False
    if env.action.tool in {"write", "edit", "database", "network", "mcp"}:
        return True
    if env.action.tool == "git":
        return any((item.git_subcommand or "") not in GIT_READONLY for item in git_items) or not git_items
    if env.action.tool == "shell":
        return True
    return _is_mutating(env, parsed)


def eval_production_database(
    env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]
) -> bool:
    if env.environment.name != "production":
        return False
    text = (env.action.command or "").lower()
    if env.action.tool == "database":
        return True
    if any(p in text for p in _DB_PATTERNS):
        return True
    return any(item.binary in _DB_BINS for item in parsed)


def eval_unknown_risky(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    if env.environment.name != "unknown":
        return False
    if env.action.tool in _RISKY_TOOLS:
        return True
    return any(item.piped_to_shell or item.is_eval or item.is_encoded for item in parsed)


def eval_modify_rules(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    return _is_write(env) and any(_matches_globs(t, _LGH_RULE_GLOBS) for t in _targets(env, parsed))


def eval_modify_config(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    return _is_write(env) and any(_matches_globs(t, _LGH_CONFIG_GLOBS) for t in _targets(env, parsed))


def eval_bypass_hooks(env: ActionEnvelope, _cfg: GuardrailConfig, _rule: dict, parsed: list[ParsedCommand]) -> bool:
    targets = _targets(env, parsed)
    if _is_write(env) and any(_matches_globs(t, _HOOK_GLOBS) for t in targets):
        name = _norm(env.action.target or "")
        if name.endswith("rules.yaml"):
            return False
        if name.endswith(".guardrail/config.yaml") or name.endswith("/config.yaml") and ".guardrail" in name:
            return False
        return True
    text = (env.action.command or "").lower()
    if "hooks" in text and any(w in text for w in ("rm ", "chmod", "unlink", "mv ")):
        return True
    if "settings.json" in text and env.action.tool in {"write", "edit", "shell"}:
        return True
    return False


EVALUATORS: dict[str, Evaluator] = {
    "write_env": eval_write_env,
    "write_pem": eval_write_pem,
    "write_ssh": eval_write_ssh,
    "read_secrets": eval_read_secrets,
    "rm_root": eval_rm_root,
    "rm_home": eval_rm_home,
    "rm_outside_repo": eval_rm_outside,
    "delete_threshold": eval_delete_threshold,
    "git_readonly": eval_git_readonly,
    "git_reset_hard": eval_git_reset_hard,
    "git_clean": eval_git_clean,
    "git_force_push": eval_git_force_push,
    "git_protected_push": eval_git_protected_push,
    "known_command": eval_known_command,
    "package_install": eval_package_install,
    "production_mutation": eval_production_mutation,
    "production_database": eval_production_database,
    "unknown_risky": eval_unknown_risky,
    "modify_lgh_rules": eval_modify_rules,
    "modify_lgh_config": eval_modify_config,
    "bypass_hooks": eval_bypass_hooks,
}


@lru_cache(maxsize=1)
def _load_builtin() -> tuple[dict[str, Any], ...]:
    raw = yaml.safe_load(read_package_text("rules", "builtin_rules.yaml")) or {}
    return tuple(raw.get("rules") or [])


def _parse(envelope: ActionEnvelope) -> list[ParsedCommand]:
    command = envelope.action.command
    if not command:
        if envelope.action.tool in {"shell", "git"} and envelope.action.operation:
            command = envelope.action.operation
        else:
            return []
    return parse_command(command)


def _match_rule(
    rule: dict[str, Any],
    envelope: ActionEnvelope,
    config: GuardrailConfig,
    parsed: list[ParsedCommand],
) -> bool:
    evaluator = EVALUATORS.get(rule.get("evaluator", ""))
    if evaluator is None:
        return False
    return evaluator(envelope, config, rule, parsed)


def _to_match(rule: dict[str, Any]) -> RuleMatch:
    return RuleMatch(
        id=str(rule.get("id", "UNKNOWN")),
        category=str(rule.get("category", "custom")),
        description=str(rule.get("description", rule.get("id", "UNKNOWN"))),
        disposition=RuleDisposition(str(rule.get("disposition", "PASS"))),
    )


def _reduce_disposition(matches: list[RuleMatch]) -> RuleDisposition:
    if not matches:
        return RuleDisposition.PASS
    disposition = matches[0].disposition
    for item in matches[1:]:
        disposition = stricter_disposition(disposition, item.disposition)
    return disposition


def evaluate_rules(envelope: ActionEnvelope, config: GuardrailConfig) -> RuleResult:
    parsed = _parse(envelope)
    if envelope.action.tool == "shell" and any(p.is_git for p in parsed):
        envelope = envelope.model_copy(
            update={"action": envelope.action.model_copy(update={"tool": "git"})}
        )
    matched: list[RuleMatch] = []
    for rule in [*_load_builtin(), *config.extra_user_rules]:
        if _match_rule(rule, envelope, config, parsed):
            matched.append(_to_match(rule))
    disposition = _reduce_disposition(matched)
    for rule in config.extra_repo_rules:
        if not _match_rule(rule, envelope, config, parsed):
            continue
        item = _to_match(rule)
        if DISPOSITION_RANK[item.disposition] < DISPOSITION_RANK[disposition]:
            continue
        matched.append(item)
        disposition = stricter_disposition(disposition, item.disposition)
    return RuleResult(matched=matched, disposition=disposition)


def matched_categories(result: RuleResult) -> set[str]:
    return {item.category for item in result.matched}


def is_known_safe(result: RuleResult) -> bool:
    return result.disposition == RuleDisposition.ALLOW
