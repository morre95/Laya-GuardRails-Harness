"""Copy only presentation aggregates from an explicitly selected backend report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "presentation" / "data" / "backend-comparison.json"
BACKENDS = ("laya_current", "laya_released", "kev")
RISKS = ("destructive_risk", "sensitive_resource", "external_impact")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    path = args.report.resolve()
    raw = path.read_bytes()
    report = json.loads(raw)
    if report["purpose"] != "benchmark" or report["mode"] != "labeled":
        parser.error("Select a labeled real-model benchmark, not an HTTP-stub smoke test.")

    backends = {}
    for name in BACKENDS:
        runtime = report["runtime"][name]
        backends[name] = {
            "risks": {
                key: {field: report["models"][name][key]["classes"]["true"][field]
                      for field in ("correct", "support")}
                for key in RISKS
            },
            "harness": {
                field: report["harness"][name]["all"]["final_decision"][field]
                for field in ("needed", "missed", "safe", "unnecessary")
            },
            "http_first_observed": report["latency"][name]["http"]["first_observed"],
            "audit_status": report["audit"][name]["status"],
            "device": runtime["before"]["declared"]["device"],
            "hardware": runtime["hardware"]["gpu"],
            "dataset_note": runtime["hardware"].get("dataset_note"),
        }
    summary = {
        "source_report": path.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
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
