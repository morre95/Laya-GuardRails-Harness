"""Copy verified model-only validation aggregates into the presentation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "presentation" / "data" / "backend-comparison.json"
BACKENDS = ("laya_current", "laya_released", "kev")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--validation-manifest", required=True, type=Path)
    args = parser.parse_args()
    path = args.report.resolve()
    raw = path.read_bytes()
    report = json.loads(raw)
    if (report["purpose"] != "benchmark" or report["mode"] != "labeled"
            or report.get("comparison_kind") != "model_only"):
        parser.error("Select a labeled real-model, model-only report.")
    validation_path = args.validation_manifest.resolve()
    validation_raw = validation_path.read_bytes()
    validation = json.loads(validation_raw)
    combined = json.loads((path.parent / "manifest.json").read_text())
    if (combined["status"] != "complete"
            or combined["report_sha256"] != hashlib.sha256(raw).hexdigest()
            or report["rows"] != validation["split"]["validation_rows"]):
        parser.error("Report is incomplete, changed or does not match the validation set.")
    for run in combined["runs"]:
        manifest = json.loads((Path(run) / "manifest.json").read_text())
        if (manifest["status"] != "complete"
                or manifest["source_dataset_sha256"] != validation["dataset_sha256"]):
            parser.error("A model pass did not use the verified slide-28 validation dataset.")

    backends = {}
    for name in BACKENDS:
        runtime = report["runtime"][name]
        support = {
            key: {label: counts["support"] for label, counts in metric["classes"].items()}
            for key, metric in report["models"][name].items()
        }
        if support != validation["support"]:
            parser.error(f"{name} class counts differ from slide 28's validation set.")
        backends[name] = {
            "classes": {
                key: {label: {field: counts[field] for field in ("correct", "support")}
                      for label, counts in metric["classes"].items()}
                for key, metric in report["models"][name].items()
            },
            "handling": {
                field: report["models"][name]["handling"]["intervention"][field]
                for field in ("needed", "missed", "safe", "unnecessary")
            },
            "http_first_pass": report["latency"][name]["http"]["first_pass"],
            "http_repeated_pass": report["latency"][name]["http"]["repeated_pass"],
            "audit_status": report["audit"][name]["status"],
            "device": runtime["before"]["declared"]["device"],
            "hardware": runtime["hardware"]["gpu"],
            "dataset_note": runtime["hardware"].get("dataset_note"),
        }
    summary = {
        "source_report": path.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "validation_manifest": validation_path.relative_to(ROOT).as_posix(),
        "validation_manifest_sha256": hashlib.sha256(validation_raw).hexdigest(),
        "dataset_role": "reused_validation",
        "comparison_kind": report["comparison_kind"],
        "rows": report["rows"],
        "purpose": report["purpose"],
        "mode": report["mode"],
        "selection": report["selection"],
        "backends": backends,
    }
    OUTPUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
