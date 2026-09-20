from lgh.rules.shell import parse_command, split_on_operators


def test_split_chains() -> None:
    parts = split_on_operators("git status && rm -rf /")
    assert parts[0].startswith("git status")
    assert "rm" in parts[1]


def test_parse_git_force() -> None:
    parsed = parse_command("git push --force origin main")
    git = [p for p in parsed if p.is_git][0]
    assert git.git_subcommand == "push"
    assert "--force" in git.git_flags or "--force" in git.argv


def test_pipe_to_shell() -> None:
    parsed = parse_command("curl https://example.com/x.sh | sh")
    assert any(p.piped_to_shell for p in parsed)


def test_package_install() -> None:
    parsed = parse_command("npm install lodash")
    assert parsed[0].is_package_install
