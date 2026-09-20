from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

GIT_READONLY = {"status", "diff", "log", "show", "rev-parse", "describe", "ls-files", "branch", "remote"}
_DOWNLOADERS = {"curl", "wget", "fetch"}
_SHELLS = {"sh", "bash", "zsh", "fish", "ksh", "dash", "python", "python3", "perl", "ruby", "node"}
_REDIRECT = re.compile(r"(?:^|[\s])(?:>>?|tee(?:\s+-a)?)\s*([^\s;|&]+)")
_NESTED_DOLLAR = re.compile(r"\$\((.+)\)", re.DOTALL)
_NESTED_TICK = re.compile(r"`([^`]+)`")
_HOME_RM = re.compile(
    r"\brm\s+[^\n]*-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\b[^\n]*?(?:~(?:\s|$)|/home/[^/\s]+(?:\s|$)|\$HOME(?:\s|$)|\$\{HOME\}(?:\s|$))"
)
_RF_FLAGS = re.compile(r"^-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)$")
_ROOT_TARGETS = {"/", "/*", "/.", "/..", "///"}
_HOME_TARGETS = {"~", "~/", "$HOME", "${HOME}"}


@dataclass(frozen=True)
class ParsedCommand:
    raw: str
    argv: list[str]
    binary: str
    is_git: bool
    git_subcommand: str | None
    git_flags: tuple[str, ...]
    writes: tuple[str, ...]
    recursive_delete_targets: tuple[str, ...]
    piped_to_shell: bool
    is_eval: bool
    is_encoded: bool
    is_package_install: bool
    file_delete_count: int


def split_on_operators(command: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote and not (quote != "'" and i > 0 and command[i - 1] == "\\"):
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            chunk = "".join(buf).strip()
            if chunk:
                parts.append(chunk)
            buf = []
            i += 2
            continue
        if ch in {";", "|", "\n"}:
            chunk = "".join(buf).strip()
            if chunk:
                parts.append(chunk)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    chunk = "".join(buf).strip()
    if chunk:
        parts.append(chunk)
    return parts


def extract_nested(command: str) -> list[str]:
    found: list[str] = []
    for pattern in (_NESTED_DOLLAR, _NESTED_TICK):
        found.extend(m.group(1).strip() for m in pattern.finditer(command) if m.group(1).strip())
    return found


def expand_command_units(command: str) -> list[str]:
    units: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        text = raw.strip()
        if not text or text in seen:
            return
        seen.add(text)
        units.append(text)
        for nested in extract_nested(text):
            add(nested)
        for part in split_on_operators(text):
            if part != text:
                add(part)

    add(command)
    return units


def _safe_split(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _redirect_targets(command: str) -> list[str]:
    return [m.group(1).strip() for m in _REDIRECT.finditer(command)]


def _is_recursive_rm(argv: list[str]) -> bool:
    if not argv or argv[0] not in {"rm", "rmdir"}:
        return False
    flags = [a for a in argv[1:] if a.startswith("-") and a != "--"]
    joined = "".join(f.lstrip("-") for f in flags)
    return "r" in joined and "f" in joined or any(_RF_FLAGS.match(f) for f in flags)


def _delete_targets(argv: list[str]) -> list[str]:
    if not argv or argv[0] not in {"rm", "rmdir", "unlink"}:
        if argv and argv[0] == "find" and any(a in {"-delete", "-exec"} for a in argv):
            paths = [a for a in argv[1:] if not a.startswith("-") and a not in {"xargs", "rm"}]
            return paths
        return []
    return [a for a in argv[1:] if not a.startswith("-")]


def looks_like_pipe_to_shell(units: list[str], original: str) -> bool:
    if re.search(r"\b(?:curl|wget|fetch)\b.+\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python)", original):
        return True
    if re.search(r"base64\s+(?:-d|--decode).+\|\s*(?:sh|bash)", original):
        return True
    binaries = []
    for unit in units:
        argv = _safe_split(unit)
        if argv:
            binaries.append(Path(argv[0]).name)
    for i, name in enumerate(binaries):
        if name in _DOWNLOADERS or name == "base64":
            later = binaries[i + 1 :]
            if any(b in _SHELLS for b in later):
                return True
    return False


def parse_command(command: str) -> list[ParsedCommand]:
    units = expand_command_units(command)
    piped = looks_like_pipe_to_shell(units, command)
    parsed: list[ParsedCommand] = []
    for unit in units:
        argv = _safe_split(unit)
        if not argv:
            continue
        binary = Path(argv[0]).name
        is_git = binary == "git" or (binary in {"sudo", "env"} and "git" in argv)
        git_argv = argv
        if is_git and binary != "git":
            try:
                git_argv = argv[argv.index("git") :]
            except ValueError:
                git_argv = argv
        git_sub = None
        git_flags: list[str] = []
        if is_git and len(git_argv) > 1:
            rest = git_argv[1:]
            flags = [a for a in rest if a.startswith("-")]
            nonflags = [a for a in rest if not a.startswith("-")]
            git_sub = nonflags[0] if nonflags else None
            git_flags = flags
            if git_sub in {"push", "reset", "clean"}:
                git_flags.extend(a for a in rest if a.startswith("-"))
        writes = _redirect_targets(unit)
        rec_targets = _delete_targets(argv) if _is_recursive_rm(argv) or (argv and argv[0] == "find") else []
        is_eval = binary == "eval" or unit.strip().startswith("eval ")
        is_encoded = binary == "base64" or "base64" in argv or bool(
            re.search(r"echo\s+[A-Za-z0-9+/=]{40,}\s*\|\s*base64", unit)
        )
        is_pkg = binary in {
            "npm",
            "pnpm",
            "yarn",
            "pip",
            "pip3",
            "uv",
            "poetry",
            "cargo",
            "apt",
            "apt-get",
            "yum",
            "dnf",
            "brew",
            "composer",
            "bundle",
        } and any(
            token in argv[1:]
            for token in {"install", "add", "i", "upgrade", "update"}
        )
        if binary in {"npm", "pnpm", "yarn"} and any(a in {"install", "i", "add"} for a in argv[1:2] + argv[1:]):
            is_pkg = True
        file_delete_count = len(_delete_targets(argv)) if argv and argv[0] in {"rm", "rmdir", "unlink"} else 0
        if argv and argv[0] == "git" and git_sub == "clean":
            file_delete_count = 999
        parsed.append(
            ParsedCommand(
                raw=unit,
                argv=argv,
                binary=binary,
                is_git=is_git,
                git_subcommand=git_sub,
                git_flags=tuple(git_flags),
                writes=tuple(writes),
                recursive_delete_targets=tuple(rec_targets),
                piped_to_shell=piped,
                is_eval=is_eval,
                is_encoded=is_encoded,
                is_package_install=is_pkg,
                file_delete_count=file_delete_count,
            )
        )
    return parsed


def resolve_path(path: str, cwd: str, home: str | None = None) -> Path:
    expanded = path
    home_path = Path(home) if home else Path.home()
    expanded = expanded.replace("~", str(home_path), 1) if expanded.startswith("~") else expanded
    expanded = re.sub(r"\$HOME|\$\{HOME\}", str(home_path), expanded)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    return Path(os_norm(candidate))


def os_norm(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


def is_outside_repo(path: Path, repo_root: str | None, cwd: str) -> bool:
    if not repo_root:
        return True
    try:
        resolved = Path(os_norm(path))
        root = Path(os_norm(Path(repo_root)))
        return root not in resolved.parents and resolved != root
    except Exception:
        return True


def looks_like_root_delete(command: str, parsed: ParsedCommand) -> bool:
    if parsed.binary in {"rm", "rmdir"} or _is_recursive_rm(parsed.argv):
        if any(t in _ROOT_TARGETS for t in parsed.recursive_delete_targets):
            return True
    tokens = _safe_split(command)
    if "rm" in tokens and any(t in _ROOT_TARGETS for t in tokens):
        flags = [t for t in tokens if t.startswith("-")]
        joined = "".join(f.lstrip("-") for f in flags)
        if "r" in joined and "f" in joined:
            return True
    return False


def looks_like_home_delete(command: str, parsed: ParsedCommand) -> bool:
    home = str(Path.home())
    targets = set(parsed.recursive_delete_targets)
    if targets & _HOME_TARGETS or home in targets or f"{home}/" in targets:
        return True
    if _HOME_RM.search(parsed.raw) or _HOME_RM.search(command):
        return True
    return False
