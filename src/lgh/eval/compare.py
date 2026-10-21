"""Frozen, inference-only comparison of two checkpoints on identical inputs."""

from __future__ import annotations

import gc
import hashlib
import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lgh.eval.metrics import percentile
from lgh.ids import utc_now_iso
from lgh.train.data import DatasetError, class_support, load_rows, question_target
from lgh.train.evaluate import _predicted_distribution, score_predictions


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_hash(row: dict) -> str:
    return hashlib.sha256(json.dumps(row["state"], sort_keys=True).encode()).hexdigest()


def read_dataset(path: Path, *, labels: Path | None = None, unlabeled: bool = False) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise DatasetError("comparison dataset is empty")
    overrides = {}
    if labels is not None:
        for line in labels.read_text().splitlines():
            if line.strip():
                label = json.loads(line)
                overrides[label["trace_id"]] = label
    rows = [row for row in rows
            if overrides.get(row.get("trace_id"), {}).get("review_status") != "insufficient_context"]
    if not rows:
        raise DatasetError("comparison dataset is empty after context exclusions")
    seen = set()
    questions = rows[0].get("questions")
    if not isinstance(questions, dict) or not questions:
        raise DatasetError("questions must be a nonempty mapping")
    for row in rows:
        trace_id = row.get("trace_id")
        if not trace_id or trace_id in seen:
            raise DatasetError(f"missing or duplicate trace_id: {trace_id}")
        seen.add(trace_id)
        if not isinstance(row.get("state"), dict) or not row.get("timestamp"):
            raise DatasetError(f"{trace_id}: state and timestamp are required")
        if row.get("questions") != questions:
            raise DatasetError(f"{trace_id}: inconsistent question set")
        override = overrides.get(trace_id)
        if override is not None:
            row["labels"] = {key: override.get(key) for key in questions}
            row["source"] = override.get("source")
        if unlabeled:
            # A blind run must never silently consume partially filled reference labels.
            row.pop("labels", None)
            row.pop("source", None)
        elif row.get("source") not in ("human", "frontier", "deterministic"):
            raise DatasetError(f"{trace_id}: independent reference labels are required; use --unlabeled otherwise")
        for key, qdef in questions.items():
            if qdef.get("type") not in ("choice", "noul"):
                raise DatasetError(f"{key}: only choice and noul questions are supported")
            if unlabeled:
                continue
            if (row.get("labels") or {}).get(key) is None:
                raise DatasetError(f"{trace_id}: missing label {key}")
            target = question_target(qdef, row["labels"][key])
            if any(not math.isfinite(p) or p < 0 or p > 1 for p in target):
                raise DatasetError(f"{trace_id}: invalid label {key}")
    return rows


def audit_dataset(rows: list[dict], training_dataset: Path | None, metadata: dict) -> dict:
    result: dict[str, Any] = {"status": "unknown", "overlap_ids": [], "overlap_states": []}
    if training_dataset is None:
        return result
    digest = file_hash(training_dataset)
    expected = metadata.get("dataset_sha256")
    if expected and digest != expected:
        raise DatasetError("--training-dataset does not match the checkpoint's dataset_sha256")
    used = load_rows(training_dataset)
    ids = {r.get("trace_id") for r in used}
    states = {state_hash(r) for r in used}
    result.update(
        training_dataset_sha256=digest,
        matches_checkpoint=bool(expected),
        overlap_ids=[r["trace_id"] for r in rows if r["trace_id"] in ids],
        overlap_states=[r["trace_id"] for r in rows if state_hash(r) in states],
    )
    result["status"] = (
        "reused" if result["overlap_ids"] or result["overlap_states"]
        else "no_exact_overlap" if expected else "unverified_training_dataset"
    )
    return result


def selected(answer: dict, qdef: dict) -> str:
    options = list(qdef["criteria"]) if qdef["type"] == "choice" else ["false", "true"]
    probs = _predicted_distribution(answer, qdef)
    return options[max(range(len(probs)), key=probs.__getitem__)]


def actual_label(label: Any, qdef: dict) -> str:
    return str(label) if qdef["type"] == "choice" else str(float(label) >= 0.5).lower()


def detailed_metrics(predictions: list[dict], rows: list[dict]) -> dict:
    questions = rows[0]["questions"]
    metrics = score_predictions(predictions, rows, questions)
    for key, qdef in questions.items():
        options = list(metrics[key]["recall"])
        matrix = {a: {p: 0 for p in options} for a in options}
        for prediction, row in zip(predictions, rows, strict=True):
            matrix[actual_label(row["labels"][key], qdef)][selected(prediction[key], qdef)] += 1
        recalls = []
        classes = {}
        for label in options:
            tp = matrix[label][label]
            support = sum(matrix[label].values())
            predicted = sum(matrix[a][label] for a in options)
            recall = tp / support if support else None
            precision = tp / predicted if predicted else None
            classes[label] = {"support": support, "correct": tp, "recall": recall, "precision": precision}
            if recall is not None:
                recalls.append(recall)
        metrics[key].update(
            confusion_matrix=matrix, classes=classes,
            balanced_accuracy=sum(recalls) / len(recalls),
            majority_baseline_accuracy=max(sum(v.values()) for v in matrix.values()) / len(rows),
        )
    if "handling" in questions:
        tp = fn = fp = tn = 0
        for prediction, row in zip(predictions, rows, strict=True):
            actual = row["labels"]["handling"] != "allow"
            predicted = selected(prediction["handling"], questions["handling"]) != "allow"
            tp += int(actual and predicted)
            fn += int(actual and not predicted)
            fp += int(not actual and predicted)
            tn += int(not actual and not predicted)
        metrics["handling"]["intervention"] = {
            "needed": tp + fn, "detected": tp, "missed": fn,
            "unnecessary": fp, "safe": tn + fp,
            "recall": tp / (tp + fn) if tp + fn else None,
            "unnecessary_rate": fp / (tn + fp) if tn + fp else None,
        }
    return metrics


def compare_predictions(base: list[dict], tuned: list[dict], rows: list[dict], unlabeled: bool) -> tuple[dict, list[dict]]:
    paired = {key: {"disagreements": 0, "improved": 0, "regressed": 0} for key in rows[0]["questions"]}
    records = []
    for row, before, after in zip(rows, base, tuned, strict=True):
        changes = {}
        for key, qdef in row["questions"].items():
            b, t = selected(before[key], qdef), selected(after[key], qdef)
            if b == t:
                continue
            paired[key]["disagreements"] += 1
            change = {"base": b, "fine_tuned": t}
            if not unlabeled:
                actual = actual_label(row["labels"][key], qdef)
                paired[key]["improved"] += int(t == actual and b != actual)
                paired[key]["regressed"] += int(b == actual and t != actual)
                change["reference"] = actual
            changes[key] = change
        if changes:
            records.append({"trace_id": row["trace_id"], "changes": changes})
    if unlabeled:
        for value in paired.values():
            value.pop("improved")
            value.pop("regressed")
    return paired, records


def _load_agent(model: str, device: str) -> tuple[Any, dict]:
    import laya
    from lgh.train.loop import resolve_checkpoint_dir

    directory = Path(resolve_checkpoint_dir(model))
    agent = laya.load(str(directory), device=device)
    agent.model.eval()
    return agent, {
        "requested": model, "resolved": str(directory.resolve()),
        "weights_sha256": file_hash(directory / "model.safetensors"),
        "config_sha256": file_hash(directory / "rl_agent_config.json"),
    }


def _predict(agent: Any, rows: list[dict], log: Callable[[str], None]) -> tuple[list[dict], dict]:
    # Warm up both checkpoints identically; exclude startup from latency measurements.
    agent.predict(rows[0]["state"], rows[0]["questions"])
    predictions, latencies = [], []
    for i, row in enumerate(rows, 1):
        start = time.perf_counter()
        answers = agent.predict(row["state"], row["questions"])["answers"]
        latencies.append((time.perf_counter() - start) * 1000)
        for key, qdef in row["questions"].items():
            probs = _predicted_distribution(answers[key], qdef)
            if any(not math.isfinite(p) or p < 0 or p > 1 for p in probs) or abs(sum(probs) - 1) > 0.001:
                raise DatasetError(f"invalid prediction for {row['trace_id']}/{key}")
        predictions.append(answers)
        if i % 25 == 0 or i == len(rows):
            log(f"  {i}/{len(rows)}")
    return predictions, {"p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95)}


def render_report(report: dict) -> str:
    lines = ["# Laya model comparison", "", f"Rows: {report['rows']}. Data audit: **{report['audit']['status']}**.", ""]
    lines.extend(f"- {note}" for note in report["notes"])
    lines.extend(["", "| Question | Base accuracy | Tuned accuracy | Majority baseline |", "|---|---:|---:|---:|"])
    if report["metrics"] is not None:
        for key, b in report["metrics"]["base"].items():
            t = report["metrics"]["fine_tuned"][key]
            lines.append(f"| {key} | {b['accuracy']:.1%} | {t['accuracy']:.1%} | {t['majority_baseline_accuracy']:.1%} |")
        lines.extend(["", "| Question / class | Base detected | Tuned detected |", "|---|---:|---:|"])
        for key, b in report["metrics"]["base"].items():
            for label, cls in b["classes"].items():
                t = report["metrics"]["fine_tuned"][key]["classes"][label]
                support = cls["support"]
                lines.append(f"| {key} / {label} | {cls['correct']}/{support} | {t['correct']}/{support} |" if support else f"| {key} / {label} | n/a | n/a |")
    else:
        lines = lines[:-2]
        lines.extend(["Reference labels are pending. Accuracy and risk recall cannot yet be measured.", ""])
    lines.extend(["", "| Question | Disagreements | Improved | Regressed |", "|---|---:|---:|---:|"])
    for key, pair in report["paired"].items():
        lines.append(f"| {key} | {pair['disagreements']} | {pair.get('improved', 'n/a')} | {pair.get('regressed', 'n/a')} |")
    return "\n".join(lines) + "\n"


def run_comparison(
    dataset: Path, trained: Path, output: Path, *, training_dataset: Path | None = None,
    base: str | None = None, device: str = "cpu", labels: Path | None = None,
    unlabeled: bool = False, allow_overlap: bool = False,
    log: Callable[[str], None] = print,
) -> dict:
    from lgh.daemon.server import MODEL_ID, resolve_device

    if output.exists():
        raise DatasetError(f"{output} already exists; choose a new --output")
    rows = read_dataset(dataset, labels=labels, unlabeled=unlabeled)
    config = json.loads((trained / "rl_agent_config.json").read_text())
    metadata = config.get("lgh_training", {})
    base = base or metadata.get("base", MODEL_ID)
    if Path(base).resolve() == trained.resolve():
        raise DatasetError("base and trained must be different checkpoints")
    audit = audit_dataset(rows, training_dataset, metadata)
    if audit["status"] != "no_exact_overlap" and not allow_overlap:
        raise DatasetError(
            f"data audit: {audit['status']}; provide the original --training-dataset and unseen test rows. "
            "--allow-overlap permits an explicitly exploratory comparison."
        )
    notes = [
        "Inference only; no training, early stopping or calibration is fitted on this dataset.",
        "Checkpoints use their saved calibration. Metrics evaluate Laya, not the full rules/policy pipeline.",
        "Overlap audit checks trace IDs and exact states against the supplied full training/validation dataset. "
        "Near-duplicates, shared sessions and earlier fine-tuning datasets are not checked.",
        "Recall uses reference noul >= 0.5; predictions use argmax (a 0.5 tie selects false). "
        "Log loss and Brier retain soft reference labels.",
        "Latency excludes one warmup per checkpoint; sequential runs are not a controlled hardware benchmark.",
    ]
    if audit["status"] != "no_exact_overlap":
        notes.append("EXPLORATORY: data independence has not been established; do not report this as an unseen test.")
    if len(rows) < 100:
        notes.append("Small test set: report counts and collect more examples before drawing conclusions.")
    if not unlabeled:
        for key, counts in class_support(rows, rows[0]["questions"]).items():
            for label, n in counts.items():
                if n < 10:
                    notes.append(f"{key}={label}: only {n} reference examples; recall is uncertain or unmeasurable.")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "dataset.jsonl"
    snapshot.write_text("".join(json.dumps(r) + "\n" for r in rows))
    predictions, models, latency = {}, {}, {}
    for name, model in (("base", base), ("fine_tuned", str(trained))):
        log(f"loading {name}: {model}")
        agent, models[name] = _load_agent(model, resolve_device(device))
        log(f"scoring {name}")
        predictions[name], latency[name] = _predict(agent, rows, log)
        del agent
        gc.collect()
        if resolve_device(device).startswith("cuda"):
            import torch
            torch.cuda.empty_cache()
    metrics = None if unlabeled else {k: detailed_metrics(v, rows) for k, v in predictions.items()}
    paired, disagreements = compare_predictions(predictions["base"], predictions["fine_tuned"], rows, unlabeled)
    report = {
        "created_at": utc_now_iso(), "rows": len(rows), "mode": "unlabeled" if unlabeled else "labeled",
        "dataset_sha256": file_hash(snapshot), "input_sha256": file_hash(dataset),
        "labels_sha256": file_hash(labels) if labels else None,
        "models": models, "device": resolve_device(device), "audit": audit,
        "metrics": metrics, "paired": paired, "latency": latency, "notes": notes,
    }
    (output / "predictions.jsonl").write_text("".join(json.dumps({
        "trace_id": row["trace_id"], "base": predictions["base"][i],
        "fine_tuned": predictions["fine_tuned"][i],
    }) + "\n" for i, row in enumerate(rows)))
    (output / "disagreements.jsonl").write_text("".join(json.dumps(r) + "\n" for r in disagreements))
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "report.md").write_text(render_report(report))
    return report
