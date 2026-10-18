# Implementation Plan: Laya vs Kev side-by-side comparison

## Overview

Decide whether Kev improves on the Laya checkpoint currently used in this guardrail harness before considering a switch. Compare identical recorded cases through both models and the same frozen rules/policy, reporting model answers and resulting harness decisions. Risk detection has priority over response speed; unnecessary interruptions are reported too. Released Laya is an additional baseline. This document is the planning deliverable; implementation and measured comparisons have not started.

Planning baseline: repository commit `1f0a47f244f8208a64f846c1eccbaa1091327606`, inspected 2026-10-18. At initial planning, `.venv/bin/python -m pytest tests/unit/test_compare.py -q` passed (9 tests). Tasks are tracked in [todo.md](todo.md). These files are being revised in place for the same work following the user's confirmed interview intent.

## Confirmed intent

- Outcome: decide whether to keep current Laya or consider replacing it with Kev.
- Primary comparison: the exact Laya checkpoint/configuration currently used, including any fine-tuning, against `jaredpalmer/kev-4b@v1.0`. Released Laya provides an additional baseline.
- Evidence: identical cases and seven typed questions, both models' answers, and the resulting decisions under the same rules and policy.
- Priority: Kev must match or improve risk detection before speed is considered. Show unnecessary interventions on safe cases alongside missed risks.
- Constraint: offline replay only. Recorded commands are text and are never executed; the active guardrail setup stays untouched.
- Out of scope: switching the active model, changing enforcement settings, calling live reviewers or humans, or training Kev during this evaluation.

## Selected model and evaluation hardware

- Kev checkpoint: **`jaredpalmer/kev-4b@v1.0`**, using its saved calibration. Resolve the tag to its concrete checkpoint commit and record that revision plus the serving-code revision in the manifest before measurement.
- Hardware: the user's **NVIDIA RTX 3090 with 24 GB VRAM**. Evaluate all model variants on this GPU; preserve and record current Laya's effective precision/calibration rather than assume it matches Kev.
- Kev runtime: **CUDA, BF16, without quantization**. Use explicit CUDA selection; do not silently fall back to CPU, a smaller checkpoint, a different revision or quantization. A changed runtime or model is a separately named experiment.
- Scheduling: run isolated evaluation models **sequentially**, with request concurrency one, to limit VRAM pressure and GPU contention. Do not stop or reconfigure the active guardrail daemon; record its GPU allocation and other GPU activity, and leave the benchmark pending if resources are insufficient.
- Capacity evidence: the [Kev-4B model card](https://github.com/jaredpalmer/kev/blob/main/docs/model-cards/kev-4b.md) describes single-24-GB-GPU operation and approximately 16 GB free for CUDA serving. This supports the planned configuration; it is not a measurement on this machine. Context length, cache and runtime buffers affect actual usage.
- Preflight: the real-model smoke test must confirm checkpoint identity, CUDA/BF16 operation, kernel compatibility, free/peak VRAM and complete seven-question responses on representative inputs before the measured run. Actual memory use and latency on the RTX 3090 remain unmeasured.

## Feature comparison

Scope: compare current Laya with Kev as alternative semantic assessors inside the same LGH rules/policy. Report model quality and offline harness outcomes separately. Hard rules, reviewer escalation, and hooks belong to LGH and are held fixed; they are not capabilities supplied by either model alone.

| Dimension | Laya in this repository | Kev | Consequence for this comparison |
|---|---|---|---|
| Role | Semantic risk sensor inside LGH; model labels do not directly issue `BLOCK` | General typed-decision model, served independently [K] | Compare model answers and replay both through the same LGH rules/policy |
| Typed answers | The frozen LGH contract uses three `choice` and four `noul` questions; upstream Laya also supports `score` [L] | Supports `choice`, `noul`, and `score` [K] | All seven current questions fit both APIs without changing labels |
| Inference | LGH calls `agent.predict(state, questions)`; upstream describes non-autoregressive inference over multiple questions [L] | Returns distributions without generating answers token by token [K] | Measure the whole seven-question request; actual packing depends on checkpoint/runtime |
| Input | Redacted structured `LayaState`, with the exact questions exported alongside each row | Accepts structured state and typed question definitions [K] | Send identical state objects, question text, criteria, and option order; internal tokenization may differ |
| API | LGH daemon exposes `POST /predict` and `GET /health` | `POST /v1/systemone`; `GET /v1/models` exposes loaded-checkpoint details [K] | A small evaluation adapter is needed; URL replacement alone is insufficient |
| Choice confidence | LGH uses the selected option's probability; its normalization code documents Laya's own entropy-based confidence | Current Kev docs define chance-adjusted top-choice confidence [K] | Score probability distributions and derive top-label probability; do not compare the raw confidence fields |
| Calibration | Existing checkpoints retain their calibration; LGH can also apply configured temperatures | Checkpoints carry fitted temperature [K] | Reproduce current Laya's effective calibration, record candidate calibration separately, and fit neither on the test set |
| Checkpoints | Identify the checkpoint actually used, including any local fine-tuning; released default is `convaiinnovations/laya-typed-decisions` | Selected checkpoint is `jaredpalmer/kev-4b@v1.0` [K] | Current Laya is the primary baseline; released Laya is additional. Resolve and record concrete checkpoint revisions |
| Runtime | Repository supports explicit CPU/CUDA selection and a resident local daemon | Selected configuration is CUDA/BF16 without quantization [K] | Use separate environments and sequential evaluation runs on the RTX 3090 (24 GB); preserve current Laya's effective configuration |
| Existing evaluation | `lgh compare` compares base vs fine-tuned Laya with overlap audits, saved predictions, and per-question metrics | Kev includes its own benchmark tooling [K] | Reuse LGH's scoring definitions for this workload rather than compare unrelated published benchmark scores |
| Enforcement integration | Already connected to LGH policy and Claude Code hooks | No Kev adapter exists in this repository | Initial work remains an offline evaluation; replacing Laya in hooks is outside scope |

Sources: [K: Kev README, API, models, calibration and serving](https://github.com/jaredpalmer/kev/blob/main/README.md); [L: Laya upstream README](https://github.com/NandhaKishorM/laya/blob/main/README.md). Documentation was retrieved through Context7 and checked against upstream where necessary. Upstream main branches can change; task 1 must pin runtime and checkpoint revisions for actual runs. In particular, current upstream Laya documentation can describe features absent from the version installed with this repository. Parameter counts and context limits for the actual Laya checkpoint must be read from its metadata, not inferred from current upstream releases.

Local evidence: `README.md`, `src/lgh/laya/questions_v0_1.yaml`, `src/lgh/laya/client.py`, `src/lgh/laya/normalize.py`, `src/lgh/daemon/server.py`, `src/lgh/eval/compare.py`, `src/lgh/train/evaluate.py`, `src/lgh/pipeline.py`, `src/lgh/policy/reducer.py`, `src/lgh/eval/export_dataset.py`, `src/lgh/eval/runner.py`, and their existing tests.

## Architecture decisions

1. Add a separate evaluation-only command, provisionally `lgh compare-backends`. Preserve the existing `lgh compare` command and its dataset-audit behavior. Reuse pure dataset/scoring helpers directly where appropriate; avoid a general provider framework or a broad refactor.
2. Use HTTP for both backends: LGH `/predict` and Kev `/v1/systemone`. Keep Kev in a separately pinned checkout/environment. Do not add its model runtime to LGH's dependencies. Adapters return raw answer distributions, not the reduced `LayaAssessment`, which discards some probabilities needed for scoring.
3. Freeze an exported JSONL dataset with `trace_id`, `timestamp`, `state`, `questions`, independent `labels`, and label `source`. Reuse `read_dataset` semantics, including label overrides, duplicate checks, complete references, soft `noul` targets, and explicit unlabeled mode. Add a replay sidecar keyed by `trace_id` containing frozen redacted action envelopes/context, session starting state, and independent action-level references. The existing export does not contain enough information to reconstruct the whole harness replay. Requests contain only state/questions plus required model routing metadata; labels never go to either model.
4. Record per-backend provenance and overlap audits. For locally fine-tuned checkpoints, require original full training/validation exports and check known IDs/state hashes using existing logic. Unknown released-model training data remains explicitly unknown; do not claim either model has never encountered similar cases. Allow exploratory runs only through an explicit flag. Auditing one model does not establish independence for the other.
5. Make current Laya vs `jaredpalmer/kev-4b@v1.0` on the RTX 3090 the main experiment, with Kev on CUDA/BF16 and sequential evaluation model runs. Read and record the actual active Laya checkpoint and effective configuration without changing them, including local checkpoint hashes and normalization temperatures. Add released Laya on the same frozen cases as an explicitly named additional baseline; deduplicate it if it is already current Laya. This is a practical replacement comparison, so report differences in training history without treating domain-tuned vs released as invalid. Training Kev is outside this evaluation.
6. Validate every returned question and option, answer type, finite probability, distribution sum (allowing documented rounding), and selected label consistency. Reject absent/extra options or invalid values instead of clipping or inventing answers. Retain the existing binary tie rule and soft-label scoring conventions.
7. Use new output directories under the already ignored `comparisons/`. Save frozen inputs, manifest, predictions, disagreements, and JSON/Markdown reports. Refuse overwrites. An incomplete run must have explicit failure status and a nonzero exit, never a successful report with dropped rows.
8. Keep execution local and read-only with respect to the actions being evaluated. Commands embedded in cases are text. Do not change hooks, daemon configuration, policy thresholds, or rules. Use loopback endpoints for the initial implementation.
9. Reuse existing rule, reducer, normalization, anti-loop, and escalation behavior through an evaluation-only wrapper or narrow replay seam. Feed the same frozen resolved environment/action context and effective rule/config snapshot to each backend's replay. Do not let host filesystem/environment detection rebuild context during replay. Initialize separate identical session stores and isolate trace output; reset them for repeated timing runs. Existing production behavior must remain unchanged.
10. Record both the policy decision and the final decision under an explicit offline reviewer policy: no live reviewer calls, reviewer unavailable, and unresolved requests remain pending human approval according to existing behavior. No approvals are fabricated and no verification skill is executed. These are final offline routing outcomes, not claims about what a live reviewer or human would decide. The manifest states this boundary and records any evaluation-only mode setting; active enforcement settings are never edited.
11. Run the seven model questions for every case to measure raw model quality. For harness replay preserve the production rule short-circuit: an overriding hard rule must ignore model answers. Report rule-controlled and model-dependent (`PASS`) cases separately, so identical rule outcomes cannot mask a model regression. Keep model timing and harness-path timing separate; rule-bypassed cases incur no model latency in the harness-path accounting.

## Dataset and experiment protocol

- Use independently labeled redacted traces collected from new sessions. Labels are assigned before viewing either model's outputs. Do not assume `kandidater.jsonl` or existing fixtures form an independent model test set; inspect their formats and provenance first. Existing `layaMock` fixtures test policy behavior, not live model quality.
- Include independent action-level references in the replay sidecar: whether intervention is needed, acceptable decisions, forbidden decisions, label source, and session/context provenance. Do not derive these references from current Laya, Kev, or historical model-driven final decisions. Validate a complete one-to-one dataset/sidecar join and state/context consistency; cases lacking replay context cannot silently count as completed harness evidence. Define which decisions satisfy each reference: asking for verification is not automatically sufficient for every dangerous action.
- Include ordinary safe edits, safe shell commands, scope drift, destructive filesystem/git actions, secrets/auth changes, external changes, and ambiguous actions. Report the support of every actual question class, including rare `replan`, `escalate`, `outside_scope`, and `irreversible` labels. Aim initially for at least 100 cases; fewer than 10 examples for a class is a warning, not reliable evidence about that class. These are collection targets, not statistical guarantees.
- Keep exact state/question payloads and option order identical. Record token counts/context behavior where observable; reject truncation or unsupported lengths rather than shorten one backend's input silently. Start with short inputs supported by both; evaluate longer inputs separately.
- Do not fit temperatures, change questions, select thresholds, or select checkpoints using the final test set. Repeated development comparisons need a separate development split; a later confirmation set comes from fresh sessions. Record known session grouping and near-duplicate limitations.
- Freeze current policy thresholds for both candidates. Reproduce current Laya's actual normalization/calibration; do not apply Laya-specific fitted temperatures to Kev. If current Laya's configuration appears to scale twice, record that limitation and retain its actual behavior for the primary baseline; any corrected configuration is a separately named later experiment. Candidate-specific tuning is outside this evaluation.
- For quality, one scored prediction per model/case is sufficient. For timing, predeclare warmup and repetition counts, record request order/cache conditions, and separate first-seen-state timing from repeated-state timing. Warm up with a separate case. Never pool warmup, failures, startup, or cache conditions into a single speed claim.
- Record the RTX 3090 identity, total/free/peak VRAM, precision, driver/runtime/checkpoint revisions, calibration, optional preprocessing and cache settings for each server. Run evaluation models sequentially with request concurrency one; record other GPU allocations, machine load and reversed-order repetitions before making speed claims. Kev uses the selected v1.0 checkpoint on CUDA/BF16 without quantization. Unknown runtime settings remain unknown and failed preflight cannot silently trigger a different configuration.

## Output and success criteria

The completed command will write:

| Artifact | Purpose |
|---|---|
| `dataset.jsonl`, `replay.jsonl` | Exact merged inputs/references, frozen replay context and independent action references, hashed after freezing |
| `manifest.json` | Protocol version, all input/context/config hashes, resolved checkpoint/code revisions, audits, RTX 3090/VRAM and precision details, sequential-run protocol, offline reviewer/session policy, timing settings and run status |
| `predictions.jsonl` | Raw/validated answers keyed `laya_current`/`kev`/`laya_released` where distinct, HTTP latency and separately named server timing |
| `decisions.jsonl` | Per-model rule matches, normalized assessment, policy/final offline decisions, bypass status, independent action references and replay timing |
| `disagreements.jsonl` | Model-answer and harness-decision disagreements, references when available, paired correctness and concrete safety regressions |
| `report.json`, `report.md` | Reliability-first comparison, model and harness measurements, support, timing, limitations, failures and selection status |

Reports show per-question accuracy, balanced accuracy, majority baseline, log loss, Brier, ECE, confusion matrices, and per-class recall/precision. Reuse `detailed_metrics` and `score_predictions` so all models share definitions. Keep model-level `handling.intervention` distinct from harness-level intervention metrics. Show paired correctness for current Laya vs Kev, with released Laya separately identified.

Harness reports show decision confusion/counts, violations of acceptable/forbidden decision references, missed needed interventions/false allows, appropriate interventions, unnecessary interruptions on safe cases, and escalation/verification/block rates with explicit denominators. Show policy and final offline decisions separately, across all cases and the model-dependent subset. Highlight cases current Laya handles safely but Kev allows or handles inadequately, plus the reverse. Treat a safe action's unjustified review/verification/replan as an interruption even when it is not a `BLOCK`.

Selection order is reliability first, speed second. A measured regression in missed risks or forbidden decisions disqualifies a faster Kev from a favorable recommendation on that evidence. Equal observed counts alone do not prove equal underlying reliability: report support and uncertainty, inspect severe/paired regressions, and mark sparse or conflicting evidence inconclusive. Only after reliability is adequate should latency inform the choice; show false-interruption tradeoffs without inventing an unagreed tolerance. Reports can recommend keeping current Laya, considering Kev, or collecting more evidence. None of these outcomes switches the active model automatically.

Latency uses client-observed HTTP p50/p95 and sample count under the declared protocol. Also record offline harness-path latency separately, including normalization, fixed rules/policy and model inference only where the production path uses it. Server-provided timings remain separately named because their boundaries can differ. No timing includes hypothetical live reviewer or human response time. Unlabeled runs show answers, offline decisions, disagreements, timing, and status only, with no accuracy/risk-recall claims or model-selection verdict. Local monetary cost is unmeasured; future rental estimates need an explicit rate and billing assumptions.

Success means a complete shared-dataset experiment compares current Laya and Kev at model and harness levels, includes the released-Laya baseline where distinct, and provides enough clearly qualified evidence to inform keeping Laya or considering Kev. An inconclusive result is valid. No recorded action executes, active setup changes, test-set fitting occurs, or case is silently excluded; existing evaluation behavior remains intact.

## Task list and dependencies

The detailed acceptance criteria, verification commands, dependencies, and likely files are in [todo.md](todo.md).

1. Freeze the experiment contract and dataset checks.
2. Prove both backend adapters on the shared question contract.
3. Prove deterministic offline harness replay.
4. Add the frozen comparison command.
5. Generate reliability-first model and harness reports.
6. Add reproducible timing and provenance.
7. Document the practical model-selection procedure.
8. Run the real-model comparison and record the evidence.

Dependency order: `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8`. Checkpoints follow tasks 2, 4, 6, and 8. Keep implementation sequential initially because replay, the runner, reports, and manifests share contracts. Each detailed task identifies its direct prerequisites.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Unknown released-model data or reused local training traces | High | Per-model audit status; freeze new sessions; explicitly label exploratory results |
| Testing a released baseline instead of the user's actual setup | High | Identify current checkpoint/config first; lead with current Laya vs Kev; label released Laya separately |
| Hard rules mask a weaker semantic model | High | Report model-only metrics and model-dependent harness cases alongside the full rule-controlled mix |
| Host state, session counters, or live review distort replay | High | Freeze context/config; isolate identical session stores; use explicit unavailable-reviewer behavior; forbid live review |
| Export lacks full envelope or independent decision references | High | Validate replay sidecar; collect missing context and blind labels before claiming harness evidence |
| Faster candidate misses additional dangerous actions | High | Reliability-first selection; inspect paired safety regressions before considering speed |
| Different confidence formulas | High | Compute metrics from distributions, with identical class ordering and tie rules |
| Cache, context handling, preprocessing, or hardware differences | High | Record settings; separate timing conditions; reject silent truncation; qualify speed results |
| Sparse rare risks and subjective soft targets | High | Show counts, soft probability metrics and label-source limitations; collect more blind labels |
| Runtime/checkpoint drift | Medium | Pin versions and revisions; preserve exact identities and hashes where available |
| Insufficient free VRAM despite 24 GB total | Medium | Sequential evaluation servers; measure free/peak VRAM and cache/context use; preserve active services and leave a resource prerequisite open if needed |
| CUDA kernel/runtime incompatibility on the RTX 3090 | Medium | Verify CUDA/BF16 and the actual kernel path in preflight; record software versions and runtime changes without silently changing model or device |
| Upstream API returns only an alias for a model | Medium | Inspect model metadata and supplied local manifest; mark identity unverified if a concrete revision is unavailable |

## Open questions before a measured run

- What exact checkpoint and effective calibration/configuration are currently used by Laya? Identify them read-only before selecting the primary baseline.
- What driver/runtime versions, kernel path and free/peak VRAM does the selected Kev-4B CUDA/BF16 setup actually use on the RTX 3090? The GPU and checkpoint are selected; smoke-test compatibility and capacity remain prerequisites.
- Which new labeled sessions, frozen replay envelopes/context, independent action-level references, and original training exports are available?
- What evidence is sufficient to establish comparable risk detection, and what increase in unnecessary interruptions would be acceptable? Until agreed before measurement, report the tradeoff and uncertainty rather than invent numerical tolerances.

These do not block producing this plan. They must be resolved or explicitly recorded as unknown before interpreting benchmark results.

## Review status

The user explicitly confirmed the intent above and requested this revision of both files. The revised tasks remain unstarted. This revision implements the agreed scope in the planning documents; it does not claim approval of unknown checkpoint choices, unagreed numerical acceptance thresholds, or any model switch. No unrelated incomplete plan was replaced.
