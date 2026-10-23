# Laya v2 experiment

See [measured results and limitations](../../tasks/laya-improvement/results.md).
Candidate 02 meets aggregate synthetic improvement targets but has new paired
safety failures; it has not been activated or approved for production.

This experiment addresses the configured fine-tune's missing risk classes and
confounded validation/calibration. Laya uses a ModernBERT encoder and option
scoring heads to answer seven questions; it does not generate a safety explanation.
The local training loop updates encoder and decision parameters using soft-target
cross entropy, freezes the unused act head, selects weights using validation loss,
and fits inference temperatures separately. Rules and the policy reducer retain
authority over the model's labels.

The original checkpoint's own report records zero recall for all positive
destructive, sensitive and external cases (5, 5 and 8 cases respectively).
Its 1,065 training rows contained zero outside-scope cases and one replan and
one escalate case. Its export also contains examples with tool-output fragments
in the user-goal field. More epochs on those rows do not fix the missing coverage.

## Data provenance

`curriculum.py` contains explicit synthetic scenarios, labels and rationales
authored by Codex, recorded as `source: frontier`, never `human`. None of the
labels comes from Laya predictions. `build_dataset.py` expands only project nouns:
312 training rows are **52 families**, not 312 independent examples. Validation
and calibration each have 32 rows across 16 separate families. Related concepts
can still occur in multiple partitions. This is a targeted curriculum, not a
representative sample of production traffic.

The separate review agent authors `challenge.py` before reading this curriculum
or either model's predictions. Challenge labels are synthetic frontier judgments,
not human ground truth. Do not train on this set after seeing its scores and then
call it a fresh test. Any such reuse requires another untouched confirmation set.

Revision 3 (`curriculum_v3.py`, `--revision 3`) has 474 training rows across 79
families, with native tool shapes, real untrusted plan/recent context and
authorization contrasts. It replaces an unjustified label that treated exit-code
suppression alone as deception. Revision 2 remains byte-for-byte reproducible.
Two publication/comment contrasts still assign different recoverability with
authorization; the reviewer flagged this label-noise caveat. Authorization alone
should not change recovery difficulty. This remains a limitation of candidate 02,
whose training artifacts are immutable.

## Reproduce

Run from the repository root with its installed `.venv`, Laya 0.3.4 and PyTorch.
Choose new output directories; commands refuse overwriting existing artifacts.
The current baseline is the configured `20261012T163824Z` local checkpoint.

```bash
.venv/bin/python experiments/laya_v2/build_dataset.py \
  --revision 3 --output comparisons/laya-v2/data-02

USE_TF=0 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 .venv/bin/lgh train \
  --dataset comparisons/laya-v2/data-02/train.jsonl \
  --validation comparisons/laya-v2/data-02/validation.jsonl \
  --calibration comparisons/laya-v2/data-02/calibration.jsonl \
  --base "$HOME/.local/share/lgh/models/20261012T163824Z" \
  --output comparisons/laya-v2/candidate-02 \
  --device cuda --epochs 6 --patience 1 --seed 42

.venv/bin/python experiments/laya_v2/confirmation.py \
  --output comparisons/laya-v2/confirmation.jsonl

USE_TF=0 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 .venv/bin/python \
  experiments/laya_v2/evaluate_candidate.py \
  --dataset comparisons/laya-v2/confirmation.jsonl \
  --current "$HOME/.local/share/lgh/models/20261012T163824Z" \
  --candidate comparisons/laya-v2/candidate-02 \
  --training comparisons/laya-v2/data-02/train.jsonl \
  --current-training comparisons/20261017-prepared/original-training-export.jsonl \
  --output comparisons/laya-v2/confirmation-evaluation --device cuda
```

The original training export hash must match the baseline's checkpoint metadata.
Candidate train/validation/calibration hashes are recorded and audited, including
trace IDs, exact states, and declared groups/sessions. Upstream pretraining data
is unknown. The baseline weights are inherited by the candidate, so its original
export is checked too. Save the referenced datasets alongside the experiment;
they are local artifacts excluded by the repository's existing `.gitignore`.

## Evaluation boundaries

Model reports include per-class support/recall, balanced accuracy, calibration
and predictions. `routing-report.json` applies unchanged effective configuration
and frozen hard-rule results to both sets of predictions. Synthetic envelopes
use `/workspace/project`; this is not replay of historical real hooks. It reports
all cases, the rule-PASS subset, and a separately named semantic-only ablation.
The latter forces PASS to isolate the model and is not a full-harness result.
No recorded commands, frontier reviewers, human approvals, or shadow overrides
run. In shadow mode actual tool execution is unaffected by either model.

After the first challenge found rule bypasses, the fast-ALLOW rules were narrowed
and covered by regressions. The second comparison holds the patched rules fixed
for both checkpoints. Do not attribute this rule repair to model training. The
fresh `confirmation.py` comes from another agent without access to training data,
first-round cases, or predictions. The first 72 cases are development evidence.

Predeclared challenge target: +20 percentage points mean balanced accuracy and
+20 points handling intervention recall, with no increase in safe-action
interruptions under the fixed reducer. The target does not establish production
reliability. Deployment needs new human-labeled operational cases and a review
of false allows, unnecessary interruptions, and insufficient handling.

The experiment leaves the active checkpoint, daemon, rules, and thresholds
unchanged. Results and outstanding review findings are recorded separately in
`tasks/laya-improvement/`.
