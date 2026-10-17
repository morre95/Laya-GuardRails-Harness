"""Collect the aggregate numbers shown in the presentation into data/metrics.json.

Run from the project root:  uv run python presentation/scripts/collect_metrics.py

Only aggregates are written. Trace contents, commands and labels stay local.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from lgh.config.loader import load_config
from lgh.eval.labels import latest_labels
from lgh.laya.questions import load_questions
from lgh.trace.reader import iter_traces

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "presentation" / "data" / "metrics.json"


def collect_traces() -> dict:
    ids: set[str] = set()
    days: set[str] = set()
    latencies: dict[str, float] = {}
    for trace in iter_traces():
        ids.add(trace.trace_id)
        days.add(trace.timestamp[:10])
        if trace.laya is not None and trace.laya.assessment is not None:
            latency = trace.laya.assessment.latency_ms
            if latency > 0:
                latencies[trace.trace_id] = latency
    values = sorted(latencies.values())
    return {
        "traces": len(ids),
        "first_day": min(days),
        "last_day": max(days),
        "days": len(days),
        "assessments": len(values),
        "latency_ms": {
            "p50": statistics.median(values),
            "p95": values[int(0.95 * (len(values) - 1))],
            "min": values[0],
        },
    }


def collect_labels(questions: dict) -> dict:
    labels = latest_labels().values()
    distribution = {}
    for key, qdef in questions.items():
        if qdef["type"] == "choice":
            counts = Counter(row[key] for row in labels)
            distribution[key] = {option: counts.get(option, 0) for option in qdef["criteria"]}
        else:
            true = sum(1 for row in labels if float(row[key]) >= 0.5)
            distribution[key] = {"false": len(labels) - true, "true": true}
    sources = Counter(row.get("source") for row in labels)
    return {"total": len(labels), "sources": dict(sources), "distribution": distribution}


def count_parameters(checkpoint: Path) -> int:
    with (checkpoint / "model.safetensors").open("rb") as handle:
        header_size = int.from_bytes(handle.read(8), "little")
        header = json.loads(handle.read(header_size))
    total = 0
    for name, info in header.items():
        if name == "__metadata__":
            continue
        size = 1
        for dim in info["shape"]:
            size *= dim
        total += size
    return total


def collect_training(checkpoint: Path) -> dict:
    report = json.loads((checkpoint / "report.json").read_text())
    config = json.loads((checkpoint / "rl_agent_config.json").read_text())
    metrics = {}
    for model, by_question in report["metrics"].items():
        metrics[model] = {
            key: {"accuracy": value["accuracy"], "log_loss": value["log_loss"], "recall": value["recall"]}
            for key, value in by_question.items()
        }
    return {
        "checkpoint": checkpoint.name,
        "base": report["base"],
        "trained_at": report["trained_at"],
        "rows": report["rows"],
        "settings": report["settings"],
        "support": report["support"],
        "warnings": report["warnings"],
        "history": report["history"],
        "temperatures": report["temperatures"],
        "metrics": metrics,
        "model": {
            "encoder": config["encoder"],
            "head_layers": config["head_layers"],
            "max_len": config["max_len"],
            "head_max_len": config["head_max_len"],
            "parameters": count_parameters(checkpoint),
        },
    }


def handling_choices(predictions: Path) -> dict:
    counts = {"base": Counter(), "fine_tuned": Counter()}
    for line in predictions.read_text().splitlines():
        row = json.loads(line)
        for model in counts:
            counts[model][row[model]["handling"]["choice"]] += 1
    return {model: dict(value) for model, value in counts.items()}


def collect_comparison() -> dict | None:
    reports = sorted((ROOT / "comparisons").glob("*/report.json"), key=lambda p: json.loads(p.read_text())["created_at"])
    if not reports:
        return None
    path = reports[-1]
    report = json.loads(path.read_text())
    metrics = None
    if report["metrics"] is not None:
        metrics = {
            model: {
                key: {"accuracy": value["accuracy"], "classes": value["classes"], "intervention": value.get("intervention")}
                for key, value in by_question.items()
            }
            for model, by_question in report["metrics"].items()
        }
    return {
        "directory": path.parent.name,
        "rows": report["rows"],
        "mode": report["mode"],
        "audit": report["audit"]["status"],
        "matches_checkpoint": report["audit"]["matches_checkpoint"],
        "paired": report["paired"],
        "handling": handling_choices(path.parent / "predictions.jsonl"),
        "metrics": metrics,
    }


def main() -> None:
    config = load_config()
    questions = load_questions()
    checkpoint = Path(config.laya.model)
    metrics = {
        "traces": collect_traces(),
        "labels": collect_labels(questions),
        "training": collect_training(checkpoint),
        "comparison": collect_comparison(),
    }
    OUTPUT.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
