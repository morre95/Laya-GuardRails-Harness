"""Aggregate traces, labels, the training report and the latest comparison into data/metrics.json.

Only aggregates are written: no commands, goals or states leave the local data directories.

    uv run python presentation/scripts/collect_metrics.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from lgh.config.loader import load_config
from lgh.eval.labels import latest_labels
from lgh.laya.questions import load_questions
from lgh.paths import traces_dir, user_data_dir

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "presentation" / "data" / "metrics.json"


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def collect_traces() -> dict:
    per_day: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    latencies: list[float] = []
    with_state = 0
    total = 0
    for path in sorted(traces_dir().glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("outcome") is not None:
                # The post hook re-appends the decision with its outcome; count each decision once.
                continue
            total += 1
            per_day[record["timestamp"][:10]] += 1
            decisions[record.get("finalDecision") or "NONE"] += 1
            if record.get("state"):
                with_state += 1
            latency = ((record.get("laya") or {}).get("assessment") or {}).get("latencyMs")
            if latency:
                latencies.append(float(latency))
    return {
        "decisions": total,
        "with_state": with_state,
        "per_day": [{"label": day, "value": count} for day, count in sorted(per_day.items())],
        "final_decisions": dict(decisions.most_common()),
        "laya_latency_ms": {
            "n": len(latencies),
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
        },
    }


def collect_labels(questions: dict) -> dict:
    latest = latest_labels(user_data_dir())
    sources = Counter(label.get("source") for label in latest.values())
    distributions = {}
    for key, qdef in questions.items():
        if qdef["type"] == "choice":
            counts = Counter(label.get(key) for label in latest.values())
            distributions[key] = {option: counts.get(option, 0) for option in qdef["criteria"]}
        else:
            values = [label.get(key) for label in latest.values() if label.get(key) is not None]
            distributions[key] = {
                "false": sum(1 for value in values if value < 0.5),
                "true": sum(1 for value in values if value >= 0.5),
            }
    return {"traces": len(latest), "sources": dict(sources), "distributions": distributions}


def majority_baseline(support: dict) -> dict:
    """Accuracy of always guessing the most common training class, on the validation split."""
    baseline = {}
    for key, train_counts in support["train"].items():
        majority = max(train_counts, key=train_counts.get)
        val_counts = support["val"][key]
        baseline[key] = {"class": majority, "accuracy": val_counts[majority] / sum(val_counts.values())}
    return baseline


def collect_training(model_dir: Path) -> dict:
    report = json.loads((model_dir / "report.json").read_text())
    return {
        "base": report["base"],
        "trained_at": report["trained_at"],
        "rows": report["rows"],
        "settings": report["settings"],
        "history": report["history"],
        "temperatures": report["temperatures"],
        "warnings": report["warnings"],
        "support": report["support"],
        "metrics": report["metrics"],
        "majority_baseline": majority_baseline(report["support"]),
    }


def collect_comparison() -> dict | None:
    reports = sorted((ROOT / "comparisons").glob("*/report.json"))
    if not reports:
        return None
    report = json.loads(reports[-1].read_text())
    return {
        "name": reports[-1].parent.name,
        "created_at": report["created_at"],
        "rows": report["rows"],
        "mode": report["mode"],
        "device": report["device"],
        "audit_status": report["audit"]["status"],
        "matches_checkpoint": report["audit"]["matches_checkpoint"],
        "disagreements": {key: value["disagreements"] for key, value in report["paired"].items()},
        "metrics": report["metrics"],
    }


def main() -> None:
    config = load_config()
    questions = load_questions()
    metrics = {
        "traces": collect_traces(),
        "labels": collect_labels(questions),
        "training": collect_training(Path(config.laya.model)),
        "comparison": collect_comparison(),
        "laya_config": {
            "timeout_seconds": config.laya.timeout_seconds,
            "thresholds": config.laya.thresholds.model_dump(),
        },
        "frontier_timeout_seconds": config.review.timeout_seconds,
    }
    OUTPUT.write_text(json.dumps(metrics, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
