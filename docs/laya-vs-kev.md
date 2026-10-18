# Spec: offline Laya vs Kev model selection

## Objective and approval basis

Implement the intent confirmed in `tasks/plan.md`: compare current Laya against
`jaredpalmer/kev-4b@v1.0`, with distinct released Laya as an additional baseline.
Risk detection takes priority over speed. The user's instruction to implement
follows the reviewed plan and task list; this document records the executable
contract without reopening the agreed scope. One capability, `model-comparison`,
contains input validation, collection, replay and reporting in that build order.

Assumptions: existing exported states/questions remain authoritative; independently
reviewed replay references must be supplied; model serving stays in separate
processes; no training or active model switch is part of implementation.

## Stack, structure and commands

Python 3.11–3.13, existing Pydantic/PyYAML, standard-library HTTP/JSON/statistics;
no new runtime dependency. Implementation: `src/lgh/eval/backend_*.py` and
`compare_backends.py`; tests: `tests/unit/test_backend_*.py` and
`test_compare_backends.py`; documentation: this file and README.

- Tests: `.venv/bin/python -m pytest -q`
- Focused tests: `.venv/bin/python -m pytest tests/unit/test_backend_contract.py -q`
- Build: `uv build`
- Help: `.venv/bin/python -m lgh.cli compare-backends --help`

Use typed, snake_case functions, frozen validated schemas and `DatasetError` for
invalid evaluation input, following existing code:

```python
def probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatasetError("probability must be a finite number")
    return float(value)
```

## Input contract

`dataset.jsonl` is the existing export format: trace_id, timestamp, state,
questions, independent labels and source. Require the exact v0.1 seven questions,
including option order. Soft binary references remain soft for probability metrics.
Unlabeled mode removes both question and action references from snapshots.

`replay.jsonl` joins exactly once per trace_id and contains:
- `envelope`: full redacted ActionEnvelope with the resolved environment at capture.
- `rules`: frozen RuleResult (matched id/category/description/disposition and total
  disposition) captured under the experiment's configuration.
- `rule_config_sha256`: hash of the resolved configuration and built-in rule text.
- `session`: initial session-store snapshot, including anti-loop counters.
- `reference`: independently labeled `requires_intervention` boolean,
  `acceptable` nonempty decision list, `forbidden` decision list and `source`.

The full envelope must deterministically rebuild the exact exported state; do not
reconstruct full envelopes from lossy compact states. Never use a prior model's
final decision as a reference. Freeze rule results at capture because rule path
resolution otherwise consults host home/symlink state. Replay validates their
configuration hash and uses the existing reducer with these identical rule results;
it does not claim to re-evaluate historical filesystem conditions. The sidecar is
trusted reviewed benchmark input, not an independent proof of rule correctness.

The experiment JSON contains `version: 1`, `purpose` (`benchmark` by default or
`synthetic_smoke` for the HTTP-stub example), a complete `config` snapshot, hardware
metadata, `backends` keyed `laya_current`, `kev`, and optionally `laya_released`, and
warmup/repetition counts. Each backend records kind, loopback URL, exact model,
resolved revision, serving-code revision, device, dtype, temperatures, training
provenance/export/hash and runtime metadata. Kev is pinned to v1.0, CUDA/BF16,
without quantization; no silent fallback. Unknown provenance requires explicit
exploratory mode. Current Laya's model and temperatures must match the snapshot.
Runtime metadata is reported as operator-supplied unless observed by the endpoint.

## Replay and collection contract

Collect each backend in its own pass and new output directory so only one
evaluation model needs GPU memory. The report command combines compatible passes.
Only loopback HTTP endpoints are accepted; disable proxies and redirects. Never
send labels, trace IDs, configuration or replay metadata to models.

Require complete, finite distributions and matching answer types/options. Compare
probabilities, not vendor confidence formulas. Reject truncated input and backend
identity mismatches. Each pass records readiness metadata before/after inference;
concrete checkpoint revisions not exposed by servers remain operator attestations.

Add a narrow frozen-state/frozen-rule input to Pipeline, leaving normal evaluate
behavior unchanged. Replay uses in-memory stores and an unavailable reviewer.
Record policy and final offline decisions separately. Evaluation uses enforce mode
only in a copied config so uncertainty requests human approval; record the actual
snapshot mode too. Never execute approvals or verification. Repeat each case from
its recorded starting state; this is action replay, not a simulated evolving session.
Hard-rule bypass is preserved, even though raw model quality is measured on all rows.

## Timing and artifacts

Warmup uses a disjoint case; abort if no such case can be constructed safely.
Cache-disabled serving is the initial recommended protocol. Record cache evidence
and label first-observed and repeated-request timings without claiming cold GPU
or uncached inference when cache status is unknown. Store every measured sample,
separate server timing and policy replay timing, and account for rule bypass.
No timing includes a real reviewer or human. Collection failures leave an explicit
incomplete manifest and exit nonzero; never reuse or overwrite a directory.

Artifacts: dataset.jsonl, replay.jsonl, experiment.json, manifest.json,
predictions.jsonl, decisions.jsonl. Combining passes adds disagreements.jsonl,
report.json and report.md. Hash all frozen inputs/config and record protocol version,
calibration, runtime revisions, hardware, ordering and sequential-pass identities.

## Testing, boundaries and success

Use meaningful failure-first pytest tests for invalid/overlapping inputs, strict
HTTP behavior with local test servers, frozen pipeline parity and isolation,
independent action references, incomplete artifacts, compatible pass joins,
reliability-first reporting and timing population accounting. Run existing tests
and package build. There is no existing numeric coverage threshold; add no skipped
tests or suppressions. Real-model evidence is distinct from mocks.

Always: validate before inference, preserve soft targets, use exact case joins,
record uncertainty and provenance, isolate every replay and output.
Ask first: adding dependencies, changing production policy/rules, model switching,
training, or relaxing an agreed acceptance requirement.
Never: execute case commands, invoke live reviewers, write active session/config
paths, silently drop a case, fit on the test set, or claim mock results are model evidence.

Success: usable per-backend collection and combined model/harness reports, regression
coverage for existing evaluation, and a real-model smoke/holdout once prerequisites
exist. A candidate with additional missed risks cannot win on speed. Without a
predeclared statistical acceptance rule or adequate evidence, the automated verdict
is inconclusive even if sample counts match; reports still show observed tradeoffs.

## Open prerequisites

Identify exact current Laya and training-export hashes; supply a blind labeled
holdout and replay context; verify the RTX 3090 CUDA driver, free/peak VRAM and
Kev serving environment; agree reliability evidence and interruption tolerances
before interpreting a favorable result. Leave real evidence tasks open if unavailable.

## Running the implemented workflow

### 1. Snapshot the current setup

```bash
.venv/bin/python -m lgh.cli compare-backends --snapshot --output comparisons/setup-3090
```

This creates `experiment.json` and `setup.json` without importing model runtimes,
loading weights, changing services, or recording API keys. Review the template:

- Current Laya's configured model, temperatures, and device are preserved. A local
  checkpoint's weight SHA-256 is recorded as its revision, and its training-data
  hash comes from checkpoint metadata. The active daemon's CLI may override its
  configured device; verify that before measuring. Its health endpoint reports a
  model name but does not attest weight bytes, device or precision.
- Set each released model's `revision` to the resolved checkpoint commit and
  `code_revision` to the serving source commit; no `latest`/`main` placeholder is
  evidence of a revision. Put current Laya's original training export path in
  `training_dataset`. Relative export paths resolve beside the experiment JSON.
- Record observed precision, preprocessing, cache settings, driver/runtime/kernel
  details and other GPU allocations in each backend's `runtime` metadata. Mark
  unavailable values as unknown. Endpoints' observable metadata is saved separately.
- Keep `kev.model` as `jaredpalmer/kev-4b@v1.0`, `device` as `cuda`, `dtype` as
  `bfloat16`, `quantized` false, and LGH `temperatures` empty. Preserve its saved
  calibration. Do not copy Laya's temperatures into Kev.
- The agreed GPU is an RTX 3090 with 24 GB. Sequential passes reduce pressure;
  this does not guarantee free VRAM or prove a particular latency. GPU snapshots
  record free memory at pass boundaries, not the true allocation peak. Obtain peak
  usage separately from the serving runtime and record how it was measured.

A prepared local template is not a completed benchmark or a verified model identity.

### 2. Prepare a blind dataset and replay sidecar

Use fresh independently labeled cases, the existing `lgh export-dataset` format
and exactly `questions_v0_1.yaml`. Supply full redacted envelopes and frozen rule
results captured with the same configuration, plus independently assigned action
references. Do not infer full envelopes from compact stored states: existing traces
retain only compact state and an envelope hash, so an export alone is insufficient.

A sidecar record has this shape (the envelope and rules must be complete objects):

```json
{
  "trace_id": "case-001",
  "envelope": {"schemaVersion": "0.1", "event": {}, "session": {}, "task": {}, "repo": {}, "environment": {}, "action": {}, "context": {}},
  "rules": {"matched": [], "disposition": "PASS"},
  "rule_config_sha256": "<configuration-and-builtins hash from setup.json>",
  "session": {"counters": {}},
  "reference": {
    "source": "human",
    "requires_intervention": true,
    "acceptable": ["REPLAN", "HUMAN_APPROVAL", "BLOCK"],
    "forbidden": ["ALLOW"]
  }
}
```

The abbreviated envelope above is a schema illustration, not valid input. Use the
`ActionEnvelope` schema for actual cases. `acceptable` is nonempty and must include
only outcomes independently judged sufficient for that action. `forbidden` cannot
intersect it. A safe case has `requires_intervention: false` and `acceptable: ["ALLOW"]`.
A verification request is not automatically sufficient for a risky action.

For newly prepared, fully known cases, capture rule results with
`evaluate_rules(envelope, experiment.config)` and obtain the binding hash with
`rule_config_hash(experiment.config)`. Historical rule results must match their
original context; do not silently recalculate them against changed filesystem state.
The replay sidecar is reviewed benchmark evidence, not proof that the rules were
historically correct. All case IDs must join exactly once and each envelope must
rebuild the exact exported redacted/compressed state. Label before reading model
answers. Original model-driven decisions and either model's predictions are not
reference labels.

### 3. Start one isolated model server at a time

Use the existing Laya environment, separate ports and the exact reviewed checkpoint.
For example, from the LGH repository, if the verified current device is CPU:

```bash
.venv/bin/python -m lgh.daemon --model /absolute/path/to/current-checkpoint --device cpu --port 8766
```

Use `--device cuda` when that is the verified baseline device. The separate released
Laya server uses `convaiinnovations/laya-typed-decisions` on port 8767. Resolve and
record the downloaded revision before collecting. Preserve current Laya's effective
precision and temperatures. A CPU-Laya/GPU-Kev result describes those concrete
configurations; do not present its latency difference as matched GPU performance.
Never stop or retarget the active guardrail daemon to run this experiment.

Install Kev from its source repository in a separate directory/environment:

```bash
git clone https://github.com/jaredpalmer/kev.git /tmp/lgh-kev
cd /tmp/lgh-kev
uv sync --extra serve
git rev-parse HEAD
KEV_DTYPE=bf16 KEV_PREFIX_CACHE=0 uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b@v1.0 --device cuda --port 8009
```

Record the serving commit and resolved model commit in the experiment, then keep
that checkout fixed across runs. Do not use the unrelated PyPI `kev` package.
The source README and [Kev-4B card](https://github.com/jaredpalmer/kev/blob/main/docs/model-cards/kev-4b.md)
are the serving references. Python 3.12/3.13 and a working CUDA stack are needed.
The first launch downloads the base and adapter. Verify `/v1/models`: pinned run,
CUDA device, BF16 dtype and `truncate_states: false`. Verify Laya `/health` similarly
for readiness and model name. Missing credentials on an authenticated local server
must be resolved in its isolated setup; this client deliberately supports plain
loopback endpoints without embedding secrets in URLs or manifests.

The initial recommended cache protocol disables Kev's prefix cache. Every report
still labels timing samples only as first-observed or repeated requests; these
labels do not establish actual cache misses/hits or cold model startup.

### 4. Collect sequential passes

From LGH, while only the matching isolated evaluation server is running:

```bash
.venv/bin/python -m lgh.cli compare-backends --dataset comparisons/holdout/dataset.jsonl --replay comparisons/holdout/replay.jsonl --experiment comparisons/setup-3090/experiment.json --backend laya_current --output comparisons/run-01/laya-current --allow-overlap
.venv/bin/python -m lgh.cli compare-backends --dataset comparisons/holdout/dataset.jsonl --replay comparisons/holdout/replay.jsonl --experiment comparisons/setup-3090/experiment.json --backend kev --output comparisons/run-01/kev --allow-overlap
.venv/bin/python -m lgh.cli compare-backends --dataset comparisons/holdout/dataset.jsonl --replay comparisons/holdout/replay.jsonl --experiment comparisons/setup-3090/experiment.json --backend laya_released --output comparisons/run-01/laya-released --allow-overlap
```

Stop only the isolated evaluation server between passes. Keep experiment, evaluator
code, case order, contexts and references unchanged. Omit the released pass when it
is the same checkpoint/revision/calibration as current Laya; the runner deduplicates
that exact baseline. `--labels /path/to/labels.jsonl` joins latest question references
by trace ID. `--unlabeled` removes all question/action references from snapshots and
suppresses quality/selection claims; replay context is still required. Set
`--timeout 60` if a verified runtime needs a larger HTTP timeout; this does not
silently convert failures to predictions.

`--allow-overlap` explicitly permits exploratory evidence. It is needed for unknown
released-model training history and is recorded prominently. A local fine-tune's
original export is checked against its checkpoint hash even in exploratory mode;
the flag does not waive a mismatched training-export hash. No flag makes an unknown
training history known. Pass failures leave an incomplete manifest and nonzero
exit; use a new output directory after correcting the cause.

### 5. Combine and inspect

```bash
.venv/bin/python -m lgh.cli compare-backends --runs comparisons/run-01/laya-current comparisons/run-01/kev comparisons/run-01/laya-released --output comparisons/run-01/report
```

The combiner requires exactly the distinct configured backends, complete case/sample
joins, unchanged artifact hashes, the same input/experiment/evaluator fingerprint,
and non-overlapping recorded collection intervals. Editing evaluator code between
passes requires recollection. Hashes detect accidental changes; manifests are not
signed proofs against a malicious operator.

Read `report.md`, inspect `disagreements.jsonl`, and use `report.json` for full
confusion matrices, class counts, policy/final decision rates and runtime evidence.
Quality uses repetition zero per case; all repetitions contribute only to their
matching timing population. Repeat-answer changes are recorded. Accounted harness
time sums measured offline replay and HTTP on model-dependent cases; it is not an
observed live hook latency and excludes real reviewer/human response time.

Keep Laya on observed safety regressions while inspecting the affected cases. If
there is no observed regression, this initial implementation returns inconclusive
until a statistical evidence rule and interruption tradeoff are agreed; it does not
turn equal sample counts into proof of equivalence or recommend switching on speed
alone. `--unlabeled` can never choose a model.

### Functional smoke without model downloads

```bash
.venv/bin/python examples/compare_backends_smoke.py --output comparisons/mock-smoke
```

This uses synthetic safe/dangerous command strings and temporary local HTTP stubs.
It exercises collection, rule bypass, joins, artifacts and reports. It executes no
case commands and provides **no real-model accuracy, GPU-memory or speed evidence**.
Run real-model smoke and an independent holdout before evaluating a switch.
