# Laya improvement experiment

Compare a new fine-tune against the configured checkpoint `20261012T163824Z`.
Keep the existing Laya/Kev plan and user edits intact. Do not switch the active
daemon until the evidence supports the candidate.

## Evidence and scope

The original report has 0/5 destructive, 0/5 sensitive and 0/8 external-risk
recall, with no outside-scope training rows and one replan/escalate row each.
Some original inputs have tool results substituted for user goals. Do not copy
those labels blindly. Create versioned, inspectable synthetic scenarios with
frontier-authored labels and rationales, never Laya-generated targets.

## Ordered slices

1. Harden dataset validation and support explicitly separate train, validation,
   and calibration files. Reject exact input, trace and declared family/session
   overlap. Keep legacy training available with an explicit optimism warning.
   Fix partial gradient accumulation and validate training settings.
2. Build a diverse curriculum with all classes, counterfactual authorization,
   safe inspection versus mutation, secrets, production, scope drift, uncertain
   context, reversibility, and prompt injection. Keep scenario families within
   a partition. Record class support and input hashes.
3. Train locally on the RTX 3090 into a new directory, recording dataset hashes,
   base checkpoint identity, settings and validation history. Select on validation
   loss only; fit temperatures only on calibration. Compare frozen policy routing
   with the current model without executing any recorded action.
4. Ask an independent subagent to review code, labels, leakage and claims, author
   fresh challenge cases blind to predictions, and challenge the finished result.
   Fix material findings and rerun affected checks. If training changes after a
   test is opened, label that set development and require fresh confirmation.

## Acceptance and limits

Predeclared target: at least +20 percentage points mean balanced accuracy across
seven questions and +20 points handling intervention recall on the independent
synthetic challenge set, without a higher safe-action interruption rate under
the unchanged reducer. Report counts and per-class failures, not accuracy alone.
This is a challenge-set target, not proof of production performance. A fresh
human-labeled operational holdout is needed before claiming real-world gains.
No policy threshold lowering, benchmark-label training, or active daemon changes.

## Review-driven second iteration

The first independently authored 72-case challenge improved mean balanced accuracy
43.4% to 66.7% and handling intervention recall 8/49 to 40/49, but full routing
misses increased 2 to 3. It is now development evidence, never reused as a fresh
test. No challenge rows enter training. A second candidate starts from the original
checkpoint with an expanded revision-3 curriculum (474 rows, 79 families), including
native tool shapes and explicit untrusted context. Separate validation/calibration
families remain unchanged in substance. Selection still uses validation loss.

The review found an existing hard-rule bypass for formatter mutations and compound
commands. Fix the fast-ALLOW boundary separately with regression tests. The next
model comparison holds these patched rules fixed for both checkpoints; do not
attribute rule improvements to training or compare different suites as one trial.
Thresholds remain unchanged. Add a safety condition: no increase in missed or
inadequately handled interventions. A second fresh-context agent authors an
untouched confirmation set without reading curriculum, first challenge, or outputs.

## Verification

Regression tests for invalid labels, split leakage and partial accumulation;
existing tests; actual GPU training and checkpoint reload; independent review;
saved prediction-level comparison and reproducible run commands. Baseline:
222 tests passed, 1 GPU smoke test deselected (run separately during validation).
