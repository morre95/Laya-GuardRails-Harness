# Laya Guardrail Harness (LGH) v0.1

Local policy enforcement between a coding agent and its tools:

```text
Rules → Laya → Policy → Frontier/Human → Execution
```

LGH decides whether a proposed action should be executed, modified, reconsidered, reviewed, or blocked. It does **not** judge whether generated code is "good code".

Default mode is **shadow**: evaluate and log, never interfere.

## Architecture

Trust hierarchy (a lower layer cannot override a harder decision):

```text
OS / sandbox → Hard Rules → Laya → Policy Reducer → Frontier Reviewer → Human
```

Laya is a semantic risk sensor, not a security authority. `BLOCK` comes from rules or policy, never from a Laya label.

Frozen v0.1 interfaces: `ActionEnvelope` → `RuleResult` → `LayaAssessment` → `GuardrailDecision` → `DecisionTrace`.

## Requirements

- Python 3.11–3.13 (`uv` pins 3.12)
- Optional GPU; CPU works (higher latency)
- Claude Code for the first adapter
- Optional `claude` CLI for frontier review

## Install

```bash
uv python pin 3.12
uv sync --extra dev
```

The Laya daemon extra pulls torch and the model runtime. Keep it on the same `uv sync` line or uv will **uninstall** it:

```bash
uv sync --extra dev --extra laya
```

CLI:

```bash
uv run lgh --help
```

Or `uv tool install .`

## Run the Laya daemon

The hook process is a thin client. The model stays resident in a localhost-only daemon (cold start is several seconds).

```bash
uv sync --extra dev --extra laya
USE_TF=0 uv run lgh daemon start
uv run lgh daemon status
uv run lgh daemon stop
```

Cold start downloads `convaiinnovations/laya-typed-decisions` on first run and can take a minute on CPU. Hooks still work in shadow mode if the daemon is down.

Binds `127.0.0.1:8765` with `POST /predict`, `GET /health`, `POST /tokens`.

Optional systemd user unit:

```ini
[Service]
ExecStart=/usr/bin/env lgh daemon start
Environment=USE_TF=0
```

If the daemon is down: shadow mode logs the failure and does not interfere; enforce mode escalates semantic cases to frontier review (then human if the reviewer is unavailable). Known-safe hard rules still `ALLOW`; known-dangerous hard rules still `BLOCK`/`HUMAN`.

## Claude Code hooks

```bash
uv run lgh install-hooks --user     # ~/.claude/settings.json
uv run lgh install-hooks --project  # ./.claude/settings.json
```

Registers `PreToolUse`, `PostToolUse`, and `Stop` with `lgh hook pre|post|stop`. Installation is idempotent and writes a `.lgh.bak` backup.

Watch traces:

```bash
uv run lgh trace tail
```

Traces: `~/.local/share/lgh/traces/*.jsonl`  
Session state: `~/.local/state/lgh/sessions/`  
User policy: `~/.config/lgh/config.yaml`

## Modes

| Mode | Behavior |
|---|---|
| `shadow` | Evaluate + log. Never interfere. **v0.1 default.** |
| `warn` | Evaluate and inject a warning as additional context. Do not block. |
| `enforce` | Full `allow` / `deny` / `ask` enforcement |

Stepwise enforce by category while the global mode stays `shadow`:

```yaml
mode: shadow
enforce_categories: [git, secrets, integrity]
```

Repo config lives in `.guardrail/config.yaml` and `.guardrail/rules.yaml`. **Repo policy is untrusted**: it can only tighten user/global policy (mode, thresholds, unions of protected lists). A repo cannot turn `git push --force → HUMAN` into `ALLOW`.

## Decisions

`ALLOW` · `ALLOW_WITH_VERIFICATION` · `REPLAN` · `FRONTIER_REVIEW` · `HUMAN_APPROVAL` · `BLOCK`

Human approval is **approve this exact action once**. There is no "always allow" for risky operations.

`ALLOW_WITH_VERIFICATION` routes to a skill (`database-safety`, `dependency-review`, `security-review`, `plan-first`, `deployment-safety`, `generic-verification`). Completing the skill does not auto-approve; the action is re-evaluated.

Anti-loop: 2 verification cycles and 2 replans per action, then frontier, then human.

## Tests and eval

```bash
uv run pytest
uv run lgh eval
```

`lgh eval --with-laya` is reserved for a live daemon; CI uses `layaMock` fixtures.

Label traces and export a fine-tune dataset (never train on Laya's own predictions):

```bash
uv run lgh label TRACE_ID --handling replan --source human
uv run lgh calibrate
uv run lgh export-dataset --output /tmp/lgh-dataset.jsonl
```

## Privacy

Traces never store secret values, API keys, tokens, `.env` contents, private keys, authorization headers, full source files, or raw credentials. Sensitive targets are logged as metadata with `contentsLogged: false`.

## v0.1 non-goals

No custom Laya checkpoint, no autonomous policy learning, no Codex parity, no GUI, no cloud service, no automatic threshold optimization.
