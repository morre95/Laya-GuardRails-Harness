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

## Laya questions (v0.1)

Laya answers seven typed questions in one forward pass (`src/lgh/laya/questions_v0_1.yaml`). `noul` is P(statement is true) on [0, 1]. `choice` is a distribution over labelled options. There is no `block` label; blocking comes from rules or policy.

| Key | Type | Asks |
|---|---|---|
| `task_alignment` | choice | How well the action is justified by the user's goal and plan: `aligned` · `supporting` · `unclear` · `outside_scope` |
| `destructive_risk` | noul | Could it delete, overwrite, corrupt, or irreversibly alter valuable state? |
| `sensitive_resource` | noul | Does it touch credentials, secrets, auth, security controls, or sensitive config? |
| `external_impact` | noul | Could it change systems, data, services, or repos outside the local workspace? |
| `reversibility` | choice | How easily can the effects be undone: `trivial` · `recoverable` · `difficult` · `irreversible` |
| `verification_needed` | noul | Should extra inspection happen before the action runs? |
| `handling` | choice | Safest proportionate handling: `allow` · `verify` · `replan` · `escalate` |

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

Or install the CLI on `PATH` (needed for Claude Code hooks and a systemd unit). `uv tool install` does **not** read `[project.optional-dependencies]`; pass the model runtime with `--with` or the tool env will only have `lgh` (systemd then fails with `No module named 'laya'`):

```bash
uv tool install --force --with laya .
"$(uv tool dir)/lgh/bin/python" -c "import laya; print('ok')"
```

## Run the Laya daemon

The hook process is a thin client. The model stays resident in a localhost-only daemon (cold start is several seconds).

```bash
uv sync --extra dev --extra laya
USE_TF=0 uv run lgh daemon start
uv run lgh daemon status
uv run lgh daemon stop
```

Cold start downloads `convaiinnovations/laya-typed-decisions` on first run and can take a minute on CPU. Hooks still work in shadow mode if the daemon is down.

Binds `127.0.0.1:8765` by default with `POST /predict`, `GET /health`, `POST /tokens`. The address comes from `laya.daemon_url` in `~/.config/lgh/config.yaml`, so hooks and daemon always agree. If another process already owns the port, `lgh daemon start` names it and refuses to start; change `daemon_url` to a free port or stop that process.

If the daemon is down: shadow mode logs the failure and does not interfere; enforce mode escalates semantic cases to frontier review (then human if the reviewer is unavailable). Known-safe hard rules still `ALLOW`; known-dangerous hard rules still `BLOCK`/`HUMAN`.

### Keep the daemon running with systemd

`lgh daemon start` is a launcher: it forks `python -m lgh.daemon`, waits until `/health` is ok, then **exits**. Do not use it as `ExecStart` with `Type=simple` — systemd will think the service died. Run the HTTP server in the foreground instead.

1. Install the CLI into a stable tool env (see above): `uv tool install --force --with laya .`. Confirm `import laya` in that interpreter before enabling the unit.
2. Confirm the interpreter that has `laya` / torch:

```bash
uv tool dir
# typically ~/.local/share/uv/tools
ls "$(uv tool dir)/lgh/bin/python"
```

3. Put the port in `~/.config/lgh/config.yaml` (`laya.daemon_url`) and use the **same** host/port in the unit. Default is `8765`. If that port is already taken, pick a free one (for example `8791`) and set `daemon_url` to match.
4. Write `~/.config/systemd/user/lgh-daemon.service`:

```ini
[Unit]
Description=LGH Laya daemon (localhost typed-decisions)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
# Foreground server. Do not ExecStart `lgh daemon start` (it forks and exits).
ExecStart=%h/.local/share/uv/tools/lgh/bin/python -m lgh.daemon --host 127.0.0.1 --port 8765 --device cpu
Environment=USE_TF=0
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=10
# First start downloads the checkpoint; CPU load can take a minute.
TimeoutStartSec=180

[Install]
WantedBy=default.target
```

Adjust `ExecStart` if `uv tool dir` is not `~/.local/share/uv/tools`, change `--port` to match `daemon_url`, and use `--device cuda` when you have an NVIDIA GPU (`gpu` is accepted as an alias). Torch does not understand the string `gpu`.

Without `uv tool install`, point `ExecStart` at this clone's `.venv/bin/python -m lgh.daemon ...`. That unit breaks if you move or delete the clone.

5. Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now lgh-daemon.service
systemctl --user status lgh-daemon.service
curl -sS http://127.0.0.1:8765/health
journalctl --user -u lgh-daemon.service -f
```

User units stop at logout unless lingering is on. For boot without a graphical session:

```bash
loginctl enable-linger "$USER"
```

The daemon does **not** attach LGH to a coding agent. You have to have to install it manually. Right now only Claude Code hooks are supported (next section). If shadow mode is on, it means the traces is only a Laya assessment that can be used as training data when it is normolized.

## Claude Code hooks

A running daemon is not enough. Claude Code only calls LGH after hooks are registered. **The first time you work in a repo**, `cd` into that repo and run this command to install it in the **project**:

```bash
lgh install-hooks --project  # .claude/settings.json
```

That writes `./.claude/settings.json` with `PreToolUse` / `PostToolUse` / `Stop` → `lgh hook pre|post|stop`. Do this once per repo.

To install it **glogaly** run this command instead:

```bash
lgh install-hooks --user    # ~/.claude/settings.json
```

Watch traces:

```bash
uv run lgh trace tail            # last 20 records as JSON
uv run lgh trace watch -n 0      # follow live, one line per decision
```

`trace watch` follows the trace log as hooks write to it, naming the rules that
matched and colouring the decision. Run it in a second terminal while a coding
agent works in any repo. The post hook re-appends a decision once the tool has
run, so those records render as an `↳ executed exit=N` line under their decision.

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

**Confidence semantics.** Laya's own `confidence` on `choice` questions is a normalized-entropy score (`1 - H(p)/log k`), not a probability. LGH stores `confidence` as the probability of the chosen label (from Laya's `probabilities`), which is what the reducer thresholds and the ECE/Brier calibration assume. Expect low values from the stock `laya-typed-decisions` checkpoint on coding-agent actions until domain calibration/fine-tuning; low confidence escalates, never allows.

**Frontier review in shadow mode** is skipped by default (`review.run_in_shadow: false`) because it cannot change behaviour there and `claude -p` costs seconds per hook. The trace keeps `policyDecision: FRONTIER_REVIEW` so the escalation rate is still measurable.

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
uv run lgh review                 # http://127.0.0.1:8770  (Ctrl-C to stop)
uv run lgh review --propose --teacher llm   # OpenRouter prefills the form
uv run lgh label TRACE_ID --source human --handling replan \
  --task-alignment outside_scope --reversibility recoverable \
  --destructive-risk 0.2 --sensitive-resource 0 --external-impact 0.1 \
  --verification-needed 0.8
uv run lgh calibrate
uv run lgh export-dataset --output /tmp/lgh-dataset.jsonl
```

`lgh review` is a localhost labeling desk. It shows the stored `LayaState` and the seven questions. Completing a label writes `~/.local/share/lgh/labels.jsonl`. Traces collected **before** this change have no state and cannot be labeled; new hook events can.

`--propose` asks a teacher LLM to prefill the seven answers for the open unlabeled trace. `--teacher llm` is the only teacher in this version; `--propose` alone defaults to it. Suggestions fill the form and are **not** saved until you click Save (the stored label is still `source: human`). Uncheck **Ask LLM** in the UI to stop proposals without restarting. Set the model in **user** config (`~/.config/lgh/config.yaml`); a repo cannot retarget it:

```yaml
teacher:
  provider: openrouter
  model: x-ai/grok-4
  base_url: https://openrouter.ai/api/v1
```

The API key is `OPENROUTER_API_KEY` in the environment, never in yaml. Missing model or key aborts before the UI listens.

## Privacy

Traces never store secret values, API keys, tokens, `.env` contents, private keys, authorization headers, full source files, or raw credentials. Sensitive targets are logged as metadata with `contentsLogged: false`. New traces also store a compact **redacted** `LayaState` (goal, plan, command, repo metadata) so a human can label the action later. That snapshot is the training input. `lgh review --propose` sends that redacted snapshot to OpenRouter; the API key stays in `OPENROUTER_API_KEY`.

## v0.1 non-goals

No custom Laya checkpoint, no autonomous policy learning, no Codex parity, no desktop/cloud console, no cloud service, no automatic threshold optimization.
