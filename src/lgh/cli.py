from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lgh import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lgh", description="Laya Guardrail Harness")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    hook = sub.add_parser("hook", help="Claude Code hook entrypoints")
    hook.add_argument("phase", choices=["pre", "post", "stop"])

    daemon = sub.add_parser("daemon", help="Manage the local Laya daemon")
    daemon.add_argument("action", choices=["start", "stop", "status"])
    daemon.add_argument("--host", default="127.0.0.1")
    daemon.add_argument("--port", type=int, default=8765)
    daemon.add_argument("--device", default="cpu")

    install = sub.add_parser("install-hooks", help="Install Claude Code hooks")
    target = install.add_mutually_exclusive_group()
    target.add_argument("--user", action="store_true", default=True)
    target.add_argument("--project", action="store_true")
    install.add_argument("--timeout", type=int, default=30)

    ev = sub.add_parser("eval", help="Run fixture evaluation")
    ev.add_argument("--fixtures", type=Path, default=None)
    ev.add_argument("--with-laya", action="store_true")

    cal = sub.add_parser("calibrate", help="Fit temperatures from labeled traces")
    cal.add_argument("--output", type=Path, default=None)

    lab = sub.add_parser("label", help="Label a trace for the dataset")
    lab.add_argument("trace_id")
    lab.add_argument("--handling", required=True)
    lab.add_argument("--source", choices=["human", "frontier", "deterministic"], required=True)
    lab.add_argument("--task-alignment", dest="task_alignment", default=None)
    lab.add_argument("--destructive-risk", dest="destructive_risk", action="store_true")
    lab.add_argument("--verification-needed", dest="verification_needed", action="store_true")

    export = sub.add_parser("export-dataset", help="Export labeled traces")
    export.add_argument("--output", type=Path, required=True)

    tail = sub.add_parser("trace", help="Inspect traces")
    tail.add_argument("action", choices=["tail"])
    tail.add_argument("-n", type=int, default=20)

    args = parser.parse_args(argv)
    if args.cmd == "hook":
        return _hook(args.phase)
    if args.cmd == "daemon":
        return _daemon(args)
    if args.cmd == "install-hooks":
        return _install(args)
    if args.cmd == "eval":
        return _eval(args)
    if args.cmd == "calibrate":
        return _calibrate(args)
    if args.cmd == "label":
        return _label(args)
    if args.cmd == "export-dataset":
        return _export(args)
    if args.cmd == "trace":
        return _trace_tail(args.n)
    return 1


def _hook(phase: str) -> int:
    if phase == "pre":
        from lgh.adapters.claude_code.pre_tool_use import run_pre

        return run_pre()
    if phase == "post":
        from lgh.adapters.claude_code.post_tool_use import run_post

        return run_post()
    from lgh.adapters.claude_code.stop import run_stop

    return run_stop()


def _daemon(args: argparse.Namespace) -> int:
    from lgh import daemon as daemon_mod

    if args.action == "start":
        daemon_mod.start(host=args.host, port=args.port, device=args.device)
        print(daemon_mod.status_text(args.host, args.port))
        return 0
    if args.action == "stop":
        daemon_mod.stop()
        return 0
    print(daemon_mod.status_text(args.host, args.port))
    return 0


def _install(args: argparse.Namespace) -> int:
    from pathlib import Path

    from lgh.adapters.claude_code.install import install_hooks

    if args.project:
        path = Path(".claude") / "settings.json"
    else:
        path = Path.home() / ".claude" / "settings.json"
    written = install_hooks(path, timeout=args.timeout)
    print(f"hooks installed at {written}")
    return 0


def _eval(args: argparse.Namespace) -> int:
    from lgh.eval.runner import run_fixtures

    root = args.fixtures
    if root is None:
        root = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
        if not root.is_dir():
            root = Path("tests/fixtures")
    summary = run_fixtures(root)
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if not summary.get("ok"):
        return 1
    return 0


def _calibrate(args: argparse.Namespace) -> int:
    from lgh.eval.calibrate import calibrate_from_traces
    from lgh.eval.labels import load_labels
    from lgh.trace.reader import iter_traces

    result = calibrate_from_traces(list(iter_traces()), load_labels())
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _label(args: argparse.Namespace) -> int:
    from lgh.eval.labels import append_label

    append_label(
        {
            "trace_id": args.trace_id,
            "handling": args.handling,
            "source": args.source,
            "task_alignment": args.task_alignment,
            "destructive_risk": args.destructive_risk,
            "verification_needed": args.verification_needed,
        }
    )
    return 0


def _export(args: argparse.Namespace) -> int:
    from lgh.eval.export_dataset import export_dataset
    from lgh.eval.labels import load_labels
    from lgh.trace.reader import iter_traces

    rows = export_dataset(list(iter_traces()), load_labels(), path=args.output)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


def _trace_tail(n: int) -> int:
    from lgh.trace.reader import tail_traces

    for trace in tail_traces(n):
        print(
            json.dumps(
                {
                    "traceId": trace.trace_id,
                    "finalDecision": str(trace.final_decision),
                    "rules": trace.rule_evaluation.matched,
                    "mode": trace.mode,
                    "timestamp": trace.timestamp,
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
