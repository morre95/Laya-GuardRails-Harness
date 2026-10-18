# Tasks: Decide whether Kev improves on current Laya

Confirmed intent and experiment design: [plan.md](plan.md). This revises the existing task list for the same work. All implementation tasks remain unstarted. Current Laya is the primary baseline; released Laya is additional. Risk detection comes before speed. Compare both model answers and offline harness decisions without executing recorded actions or changing the active setup.

Selected candidate: **`jaredpalmer/kev-4b@v1.0`**, resolved to a concrete checkpoint revision before measurement. Evaluation hardware: **NVIDIA RTX 3090, 24 GB VRAM**. Kev uses **CUDA/BF16 without quantization**; run isolated evaluation models **sequentially**, with request concurrency one. Preserve current Laya's effective configuration. The smoke test must verify compatibility and actual free/peak VRAM; capacity and latency have not been measured on this machine. No silent model/device/precision fallback or active-daemon reconfiguration is allowed.

Verification commands below apply when their referenced tests exist. The final package build check is `uv build`; isolated evaluation modules do not each need a package build.

## Task 1: Freeze the model-selection experiment contract

**Description:** Identify the exact current Laya checkpoint and effective configuration read-only. Define shared model inputs, replay context, independent references, audits and outputs. Resolve `jaredpalmer/kev-4b@v1.0` to a concrete revision and record RTX 3090/CUDA/BF16 settings plus the additional released-Laya baseline without inventing identities or numerical acceptance thresholds.

**Acceptance criteria:**
- [ ] Define `laya_current`, `kev` (`jaredpalmer/kev-4b@v1.0` with resolved revision), and distinct `laya_released`, revisions/calibration, identical inputs, probability/tie conventions, fixed rules/policy, offline reviewer behavior and reliability-first selection. Record RTX 3090 24 GB, Kev CUDA/BF16 without quantization, sequential scheduling and no silent fallback; deduplicate identical Laya baselines.
- [ ] Validate complete independent model labels and one-to-one replay sidecars containing frozen redacted envelopes/environment, session starting state, intervention-needed and acceptable/forbidden decision references. Reject missing/mismatched context and duplicate/inconsistent inputs; retain soft targets and valid label overrides.
- [ ] Define per-model training-overlap/provenance states and explicit exploratory/unlabeled modes. Unknown training histories and unagreed reliability/false-interruption tolerances remain visible; no unsupported selection verdict is allowed.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_backend_contract.py tests/unit/test_compare.py -q` passes.
- [ ] Inspect the current-checkpoint record, synthetic dataset/sidecar and policy snapshot. Confirm references are independent of model outputs and historical final decisions.

**Dependencies:** None.

**Files likely touched:**
- `docs/laya-vs-kev.md` (new protocol)
- `src/lgh/eval/backend_contract.py` (new)
- `tests/unit/test_backend_contract.py` (new)

**Estimated scope:** Medium: 3 files.

## Task 2: Prove the backend adapters

**Description:** Implement evaluation-only HTTP adapters preserving raw distributions and loaded-model identity. Use isolated evaluation servers/environments for Laya variants and Kev; do not restart or retarget the active daemon.

**Acceptance criteria:**
- [ ] Laya uses `/predict`; Kev uses `/v1/systemone`. Each receives identical state/questions/criteria order, no labels or replay-only metadata, and returns all seven validated answers.
- [ ] Tests reject timeouts, non-JSON/error responses, missing/extra questions/options, inconsistent selected labels, NaN/out-of-range values and invalid probability sums, allowing documented rounding. Failures never become fabricated safe answers.
- [ ] Record concrete loaded identities versus aliases, current Laya's effective normalization temperatures and candidate calibration separately. Score distributions rather than raw confidence fields.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_eval_backends.py tests/unit/test_backend_contract.py -q` passes against mock local HTTP servers.
- [ ] Inspect requests and known distributions for label isolation, criteria order and `noul = P(true)` semantics.

**Dependencies:** Task 1.

**Files likely touched:**
- `src/lgh/eval/backends.py` (new)
- `src/lgh/eval/backend_contract.py`
- `tests/unit/test_eval_backends.py` (new)

**Estimated scope:** Medium: 3 files.

## Checkpoint: Baselines and compatibility (after tasks 1–2)

- [ ] Existing comparison tests and new contract/adapter tests pass.
- [ ] Current Laya is the primary baseline; additional released Laya and selected Kev are explicitly identified.
- [ ] Shared inputs, replay references and provenance have concrete records. The selected RTX 3090 24 GB / Kev-4B v1.0 CUDA/BF16 configuration is recorded; runtime compatibility and actual free/peak VRAM remain smoke-test prerequisites.

## Task 3: Prove deterministic offline harness replay

**Description:** Reuse existing rule, reducer, normalization, anti-loop and escalation behavior through an evaluation wrapper or narrow replay seam. Feed frozen context/configuration and record both policy and final offline decisions, retaining production defaults.

**Acceptance criteria:**
- [ ] Both models use the same frozen action/environment/configuration and separate identical starting session stores. Replay cannot redetect host state, call live reviewers/humans, execute commands/verification skills, or write active stores/config. An explicit unavailable-reviewer policy routes unresolved review to existing pending-human behavior.
- [ ] Hard rules retain precedence irrespective of model answers; `PASS` cases can reflect model differences. Save matches, bypass status, normalized assessments and policy/final offline decisions. Fixed-input tests establish parity with existing pipeline behavior.
- [ ] Reproduce current Laya's effective calibration without applying Laya-specific temperatures to Kev. Cover all decision routes, uncertainty, anti-loop limits and repeat isolation; pending approval never counts as granted approval or execution.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_backend_replay.py tests/unit/test_pipeline.py tests/unit/test_reducer.py tests/unit/test_modes.py -q` passes.
- [ ] Tests fail on attempted process execution, live review, host detection or active-store writes. Replays with the same starting state give identical decisions.

**Dependencies:** Tasks 1–2.

**Files likely touched:**
- `src/lgh/eval/backend_replay.py` (new)
- `tests/unit/test_backend_replay.py` (new)
- `src/lgh/pipeline.py` (only if a narrow replay seam is necessary)
- `tests/unit/test_pipeline.py` (default-path regression coverage if needed)

**Estimated scope:** Medium: 2–4 files.

## Task 4: Add the frozen comparison command

**Description:** Add `lgh compare-backends` with dataset/replay inputs, policy snapshot, output, endpoints/identities, labels, unlabeled mode, timeout and exploratory-audit options. Freeze inputs and orchestrate inference plus replay for the primary pair and additional released baseline.

**Acceptance criteria:**
- [ ] Write hashed `dataset.jsonl`, `replay.jsonl`, manifest, per-model predictions and `decisions.jsonl` with complete case joins. Ask all model questions for quality scoring while preserving hard-rule bypass during harness replay. Refuse output overwrites.
- [ ] Complete audits and context validation before inference. Failures produce incomplete status and nonzero exit; no cases or additional-baseline failures disappear silently and no incomplete run gets a favorable verdict.
- [ ] The command cannot change active hooks, model selection, rules, thresholds or config; existing `lgh compare` arguments, audits and outputs retain their behavior.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_compare_backends.py tests/unit/test_backend_replay.py tests/unit/test_compare.py -q` passes, including CLI, baseline deduplication, missing-context and partial-failure tests.
- [ ] `.venv/bin/python -m lgh.cli compare-backends --help` describes model and replay inputs.
- [ ] Inspect a complete mock experiment: frozen artifacts distinguish rule-controlled and model-dependent cases.

**Dependencies:** Tasks 1–3.

**Files likely touched:**
- `src/lgh/cli.py`
- `src/lgh/eval/compare_backends.py` (new)
- `tests/unit/test_compare_backends.py` (new)

**Estimated scope:** Medium: 3 files.

## Checkpoint: Offline decision flow (after tasks 3–4)

- [ ] New replay/runner tests and existing pipeline/reducer/mode/compare tests pass.
- [ ] Fixtures demonstrate hard-rule precedence, model-dependent decisions and explicit pending approval outcomes.
- [ ] Complete mock artifacts exist; active setup is unchanged and no recorded action has executed.

## Task 5: Generate reliability-first model and harness reports

**Description:** Compare current Laya and Kev at model and harness levels, with released Laya separately identified. Reuse probability-scoring helpers and score action decisions using independent references.

**Acceptance criteria:**
- [ ] Model reports include all plan-specified per-question metrics and class support. Harness reports show policy/final decisions, acceptable/forbidden violations, missed required interventions, false allows, unnecessary interruptions and escalation/verification/block rates, with denominators for all cases and `PASS` cases.
- [ ] Paired disagreements expose current-Laya-only and Kev-only correct/safe outcomes, including current-safe/Kev-unsafe regressions. Keep model handling metrics distinct from harness interventions; cover ties, soft targets, missing classes, safe-case interruptions and rule-masked errors.
- [ ] Reliability precedes speed: a faster Kev cannot excuse worse risk detection. Sparse/conflicting evidence is inconclusive; equal observed counts do not prove equivalence. Unlabeled/incomplete runs make no correctness or selection claims; reports never switch models.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_backend_report.py tests/unit/test_compare_backends.py tests/unit/test_compare.py -q` passes.
- [ ] Inspect fixtures with a faster Kev missing an extra risk, an unnecessary verification request on a safe action, a rule-masked model error and an absent rare class; verify counts and conclusions.

**Dependencies:** Tasks 3–4.

**Files likely touched:**
- `src/lgh/eval/backend_report.py` (new)
- `src/lgh/eval/compare_backends.py`
- `tests/unit/test_backend_report.py` (new)

**Estimated scope:** Medium: 3 files.

## Task 6: Record reproducible response timing and provenance

**Description:** Measure HTTP and offline harness-path response times as separate populations. Model-only inference on rule-bypassed cases is excluded from harness-path timing; hypothetical live reviewer/human latency is never included.

**Acceptance criteria:**
- [ ] Record warmup/repetition/order/cache protocol, resolved checkpoint/code revisions, RTX 3090 identity and total/free/peak VRAM, driver/runtime/kernel/precision/calibration details, frozen hashes and offline reviewer policy. Run isolated evaluation models sequentially at concurrency one; record other GPU activity, mark unknown values and preserve active settings.
- [ ] Report HTTP p50/p95/sample counts separately from server and harness timing, split by first-seen/repeated states and rule-controlled/model-dependent paths. Account separately for startup/warmup/failures; reset replay stores for repeats.
- [ ] Controlled-clock tests verify timing populations and bypass accounting. Qualify unmatched hardware/cache conditions, consider speed after reliability, and leave local monetary cost unmeasured.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/unit/test_compare_backends.py tests/unit/test_backend_report.py tests/unit/test_backend_replay.py -q` passes.
- [ ] Inspect samples for correct warmup/failure/startup/bypass exclusion and no invented reviewer/human time.

**Dependencies:** Tasks 4–5.

**Files likely touched:**
- `src/lgh/eval/compare_backends.py`
- `src/lgh/eval/backend_report.py`
- `tests/unit/test_compare_backends.py`
- `tests/unit/test_backend_report.py`

**Estimated scope:** Medium: 4 files.

## Checkpoint: Selection evidence and timing (after tasks 5–6)

- [ ] Reports distinguish model quality, policy/final offline outcomes and rule-controlled/model-dependent cases.
- [ ] Fixtures prove speed cannot override a safety regression and insufficient evidence remains inconclusive.
- [ ] Timing/provenance support the current-Laya/Kev comparison with released-Laya context and explicit simulation boundaries.

## Task 7: Document the practical model-selection procedure

**Description:** Explain current-baseline identification, isolated pinned servers, independent dataset/replay references, actual CLI usage and reliability-first interpretation without changing the active setup.

**Acceptance criteria:**
- [ ] Cover current Laya/calibration, distinct released Laya, and isolated `jaredpalmer/kev-4b@v1.0` source-based CUDA/BF16 serving without quantization on the RTX 3090 24 GB. Include sequential scheduling, readiness/identity, kernel and free/peak-VRAM checks; use Kev's repository rather than the unrelated PyPI `kev` package.
- [ ] Explain dataset/sidecar/config preparation, implemented CLI examples, outputs, overlap checks, independent labels, offline reviewer/session policy and timing boundaries. No step executes a recorded command or changes hooks/models/enforcement.
- [ ] Explain keep Laya, consider Kev and inconclusive outcomes, with risk detection before speed and explicit interruption/uncertainty tradeoffs. Switching models and training Kev remain separate future decisions.

**Verification:**
- [ ] Check examples against implemented CLI help and generated mock artifacts.
- [ ] `.venv/bin/python -m pytest -q` passes; `uv build` succeeds before the measured experiment.

**Dependencies:** Tasks 1–6.

**Files likely touched:**
- `README.md`
- `docs/laya-vs-kev.md`

**Estimated scope:** Small: 2 files.

## Task 8: Run the real-model comparison

**Description:** Perform a real-model smoke experiment, then a blind labeled holdout comparison when checkpoints, hardware, replay context and independent references are available. Record practical evidence; keep unmet prerequisites open rather than substitute mocks for model evidence.

**Acceptance criteria:**
- [ ] On the RTX 3090 24 GB, sequential smoke runs verify seven answers per case for current Laya, `jaredpalmer/kev-4b@v1.0` and distinct released Laya, complete replay decisions, resolved identities, Kev CUDA/BF16 operation, kernel compatibility, free/peak VRAM and no truncation. Active setup remains unchanged; no recorded action executes and no fallback silently changes the candidate.
- [ ] The holdout produces all artifacts with class/risk support, per-model audit status, rule-controlled/model-dependent outcomes and comparable timing. Resolve unagreed reliability evidence and false-interruption tolerances before measurement or leave them explicitly undecided in the conclusion.
- [ ] Record a qualified keep-current-Laya / consider-Kev / inconclusive result and paired safety evidence. Missing hardware/data/context leaves corresponding criteria incomplete; no automatic switch or Kev training occurs.

**Verification:**
- [ ] Follow the documented procedure with isolated real-model servers; inspect manifest, both input files, predictions, decisions, disagreements and JSON/Markdown reports.
- [ ] Repeat frozen inputs in a fresh directory with reset stores: input/config/model identity hashes match; changed predictions or timing variation remain visible.
- [ ] Review concrete missed-risk and unnecessary-interruption cases against blind references before interpreting speed.

**Dependencies:** Tasks 1–7; identified current Laya and released-Laya checkpoints, resolved `jaredpalmer/kev-4b@v1.0`, working CUDA/BF16 runtime and sufficient free VRAM on the RTX 3090 24 GB, independent holdout labels, frozen replay context/configuration and relevant original training exports.

**Files likely touched:**
- `docs/laya-vs-kev.md` (summary and local artifact paths without trace contents)
- `tasks/todo.md` (verification evidence and unmet prerequisites)

**Estimated scope:** Small: 2 tracked files; generated artifacts remain under ignored `comparisons/`.

## Checkpoint: Practical model-selection review (after tasks 7–8)

- [ ] Full tests/build pass and documentation matches the implemented procedure.
- [ ] Real-model smoke and blind holdout evidence are distinct; missing prerequisites remain unchecked and uncertainty stays visible.
- [ ] User receives a reliability-first current-Laya/Kev comparison with released-Laya context, replay boundaries and interruption/latency tradeoffs.
- [ ] Active model, hooks, enforcement settings, rules and thresholds are unchanged. A later model switch or Kev training is a separate task.
