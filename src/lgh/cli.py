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
    daemon.add_argument("--host", default=None, help="default: from laya.daemon_url in config")
    daemon.add_argument("--port", type=int, default=None, help="default: from laya.daemon_url in config")
    daemon.add_argument(
        "--device",
        default="cpu",
        help="torch device (cpu, cuda). 'gpu' is an alias for cuda.",
    )

    install = sub.add_parser("install-hooks", help="Install Claude Code hooks")
    target = install.add_mutually_exclusive_group()
    target.add_argument("--user", action="store_true", default=True)
    target.add_argument("--project", action="store_true")
    install.add_argument("--timeout", type=int, default=30)

    ev = sub.add_parser("eval", help="Run fixture evaluation")
    ev.add_argument("--fixtures", type=Path, default=None)
    ev.add_argument("--with-laya", action="store_true")

    compare = sub.add_parser("compare", help="Compare two checkpoints on a frozen dataset (no training)")
    compare.add_argument("--dataset", type=Path, required=True)
    compare.add_argument("--trained", type=Path, required=True, help="fine-tuned checkpoint directory")
    compare.add_argument("--output", type=Path, required=True, help="new directory for frozen inputs and reports")
    compare.add_argument("--training-dataset", type=Path, help="original full export, including validation rows")
    compare.add_argument("--base", help="default: base recorded in the trained checkpoint")
    compare.add_argument("--device", default="cpu")
    compare.add_argument("--labels", type=Path, help="labels.jsonl overrides, joined by trace_id")
    compare.add_argument("--unlabeled", action="store_true", help="compare predictions without accuracy claims")
    compare.add_argument("--allow-overlap", action="store_true", help="explicitly allow exploratory/reused data")

    backends = sub.add_parser("compare-backends", help="Collect one model pass or combine offline Laya/Kev passes")
    backends.add_argument("--dataset", type=Path)
    backends.add_argument("--replay", type=Path, help="frozen rule/context/reference JSONL sidecar")
    backends.add_argument("--experiment", type=Path, help="frozen policy and backend identity JSON")
    backends.add_argument("--backend", choices=["laya_current", "kev", "laya_released"])
    backends.add_argument("--runs", nargs="+", type=Path, help="combine completed per-backend directories")
    backends.add_argument("--snapshot", action="store_true", help="write a read-only current-config experiment template")
    backends.add_argument("--output", type=Path, required=True, help="new output directory")
    backends.add_argument("--labels", type=Path)
    backends.add_argument("--unlabeled", action="store_true")
    backends.add_argument("--allow-overlap", action="store_true", help="explicit exploratory audit override")
    backends.add_argument("--timeout", type=float, default=30)

    cal = sub.add_parser("calibrate", help="Fit temperatures from labeled traces")
    cal.add_argument("--output", type=Path, default=None)

    lab = sub.add_parser("label", help="Label a trace for the dataset")
    lab.add_argument("trace_id")
    lab.add_argument("--source", choices=["human", "frontier", "deterministic"], required=True)
    lab.add_argument("--handling", required=True, choices=["allow", "verify", "replan", "escalate"])
    lab.add_argument(
        "--task-alignment",
        dest="task_alignment",
        required=True,
        choices=["aligned", "supporting", "unclear", "outside_scope"],
    )
    lab.add_argument(
        "--reversibility",
        required=True,
        choices=["trivial", "recoverable", "difficult", "irreversible"],
    )
    lab.add_argument("--destructive-risk", dest="destructive_risk", type=float, required=True)
    lab.add_argument("--sensitive-resource", dest="sensitive_resource", type=float, required=True)
    lab.add_argument("--external-impact", dest="external_impact", type=float, required=True)
    lab.add_argument("--verification-needed", dest="verification_needed", type=float, required=True)

    export = sub.add_parser("export-dataset", help="Export labeled traces")
    export.add_argument("--output", type=Path, required=True)

    train = sub.add_parser("train", help="Fine-tune Laya on an exported dataset")
    train.add_argument("--dataset", type=Path, required=True, help="output of `lgh export-dataset`")
    train.add_argument("--output", type=Path, default=None, help="default: <data dir>/models/<UTC time>")
    train.add_argument("--base", default=None, help="base checkpoint (default: the stock Laya model)")
    train.add_argument("--epochs", type=int, default=4)
    train.add_argument("--device", default="cuda", help="torch device (cpu, cuda). 'gpu' is an alias for cuda.")

    review = sub.add_parser("review", help="Open a local UI for labeling traces")
    review.add_argument("--host", default="127.0.0.1")
    review.add_argument("--port", type=int, default=8770)
    review.add_argument("--no-browser", action="store_true")
    review.add_argument(
        "--propose",
        action="store_true",
        help="Ask a teacher LLM to prefill labels (not saved until you confirm)",
    )
    review.add_argument(
        "--teacher",
        default=None,
        metavar="KIND",
        help="Teacher when --propose is set (default: llm). Only 'llm' is supported.",
    )

    triage = sub.add_parser("triage", help="Rank skipped/unlabeled traces by likely risk")
    triage.add_argument("-n", type=int, default=50, help="max candidates to print")
    triage.add_argument("--min-score", dest="min_score", type=int, default=1)
    triage.add_argument("--json", action="store_true", help="one JSON object per line")

    tail = sub.add_parser("trace", help="Inspect traces")
    tail.add_argument("action", choices=["tail", "watch"])
    tail.add_argument("-n", type=int, default=20, help="backlog records; 0 starts watch on an empty screen")

    args = parser.parse_args(argv)
    if args.cmd == "hook":
        return _hook(args.phase)
    if args.cmd == "daemon":
        return _daemon(args)
    if args.cmd == "install-hooks":
        return _install(args)
    if args.cmd == "eval":
        return _eval(args)
    if args.cmd == "compare":
        return _compare(args)
    if args.cmd == "compare-backends":
        return _compare_backends(args)
    if args.cmd == "calibrate":
        return _calibrate(args)
    if args.cmd == "label":
        return _label(args)
    if args.cmd == "export-dataset":
        return _export(args)
    if args.cmd == "train":
        return _train(args)
    if args.cmd == "review":
        return _review(args)
    if args.cmd == "triage":
        return _triage(args)
    if args.cmd == "trace":
        if args.action == "watch":
            return _trace_watch(args.n)
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
    from lgh.config.loader import load_config

    config = load_config(cwd=".")
    cfg_host, cfg_port = daemon_mod.endpoint_from_url(config.laya.daemon_url)
    host = args.host or cfg_host
    port = args.port or cfg_port
    if (host, port) != (cfg_host, cfg_port):
        print(
            f"warning: starting on {host}:{port} but hooks will call "
            f"{config.laya.daemon_url}; set laya.daemon_url in config to match.",
            file=sys.stderr,
        )
    if args.action == "start":
        try:
            daemon_mod.start(host=host, port=port, device=args.device, model=config.laya.model)
        except daemon_mod.DaemonError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(daemon_mod.status_text(host, port))
        return 0
    if args.action == "stop":
        daemon_mod.stop()
        return 0
    print(daemon_mod.status_text(host, port))
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


def _compare(args: argparse.Namespace) -> int:
    from lgh.eval.compare import run_comparison
    from lgh.train.data import DatasetError

    try:
        report = run_comparison(
            args.dataset, args.trained, args.output, training_dataset=args.training_dataset,
            base=args.base, device=args.device, labels=args.labels,
            unlabeled=args.unlabeled, allow_overlap=args.allow_overlap,
        )
    except (DatasetError, OSError, ValueError, KeyError, ImportError) as exc:
        print(f"comparison error: {exc}", file=sys.stderr)
        return 1
    print(f"{report['rows']} rows; data audit: {report['audit']['status']}")
    print(f"report: {args.output / 'report.md'}")
    return 0


def _compare_backends(args: argparse.Namespace) -> int:
    from lgh.eval.compare_backends import collect_backend, combine_runs

    try:
        if args.snapshot:
            if any((args.dataset, args.replay, args.experiment, args.backend, args.runs, args.labels,
                    args.unlabeled, args.allow_overlap)):
                raise ValueError("--snapshot cannot be combined with collection or report options")
            from lgh.eval.backend_setup import snapshot_experiment

            snapshot_experiment(args.output, cwd=Path.cwd())
            print(f"review and complete the experiment template: {args.output / 'experiment.json'}")
        elif args.runs:
            if any((args.dataset, args.replay, args.experiment, args.backend, args.labels,
                    args.unlabeled, args.allow_overlap)):
                raise ValueError("--runs cannot be combined with collection options")
            result = combine_runs(args.runs, args.output)
            print(f"report: {args.output / 'report.md'}; selection: {result['selection']['status']}")
        else:
            if not all((args.dataset, args.replay, args.experiment, args.backend)):
                raise ValueError("collection requires --dataset, --replay, --experiment and --backend")
            result = collect_backend(args.dataset, args.replay, args.experiment, args.backend,
                                     args.output, labels=args.labels, unlabeled=args.unlabeled,
                                     allow_overlap=args.allow_overlap, timeout=args.timeout)
            print(f"collected {result['sample_count']} samples: {args.output}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"backend comparison error: {exc}", file=sys.stderr)
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


def _train(args: argparse.Namespace) -> int:
    import time

    from lgh.daemon import laya_installed
    from lgh.daemon.server import MODEL_ID
    from lgh.paths import user_data_dir
    from lgh.train.data import DatasetError

    if not laya_installed():
        print("lgh train needs the Laya runtime: uv sync --extra dev --extra laya", file=sys.stderr)
        return 1
    output = args.output or user_data_dir() / "models" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if output.exists():
        print(f"{output} already exists; pick a new --output", file=sys.stderr)
        return 1

    from lgh.train.loop import TrainSettings
    from lgh.train.runner import run_training, summary_table

    try:
        report = run_training(
            args.dataset,
            output,
            base=args.base or MODEL_ID,
            device=args.device,
            settings=TrainSettings(epochs=args.epochs),
        )
    except DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 1
    print(summary_table(report))
    print(f"checkpoint: {report['checkpoint']}")
    print(f"report: {output / 'report.json'}")
    print("To serve it, set laya.model to the checkpoint path in ~/.config/lgh/config.yaml and restart the daemon.")
    return 0


def _label(args: argparse.Namespace) -> int:
    from lgh.eval.labels import LabelError, append_label

    try:
        append_label(
            {
                "trace_id": args.trace_id,
                "source": args.source,
                "handling": args.handling,
                "task_alignment": args.task_alignment,
                "reversibility": args.reversibility,
                "destructive_risk": args.destructive_risk,
                "sensitive_resource": args.sensitive_resource,
                "external_impact": args.external_impact,
                "verification_needed": args.verification_needed,
            }
        )
    except LabelError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _review(args: argparse.Namespace) -> int:
    from lgh.review.server import serve
    from lgh.teacher import TeacherError, resolve_teacher

    try:
        teacher = resolve_teacher(args.propose, args.teacher)
    except TeacherError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        serve(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            teacher=teacher,
        )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _export(args: argparse.Namespace) -> int:
    from lgh.eval.export_dataset import export_dataset
    from lgh.eval.labels import load_labels
    from lgh.trace.reader import iter_traces

    rows = export_dataset(list(iter_traces()), load_labels(), path=args.output)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


def _triage(args: argparse.Namespace) -> int:
    from lgh.review.queue import ReviewStore

    candidates = ReviewStore().risk_candidates(min_score=args.min_score)
    for row in candidates[: args.n]:
        if args.json:
            print(json.dumps(row))
            continue
        summary = row["summary"] if len(row["summary"]) <= 100 else row["summary"][:97] + "..."
        print(f"{row['risk']:>3}  {row['traceId']}  {row['status']:<9}  {summary}")
        print(f"     {' '.join(row['riskReasons'])}")
    print(f"{len(candidates)} candidates (showing {min(args.n, len(candidates))})", file=sys.stderr)
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


def _trace_watch(backlog: int) -> int:
    from lgh.paths import traces_dir
    from lgh.trace.watch import follow_traces, format_trace

    color = sys.stdout.isatty()
    print(f"watching {traces_dir()} — Ctrl-C to stop", file=sys.stderr)
    previous = None
    try:
        for trace in follow_traces(backlog=backlog):
            print(format_trace(trace, previous=previous, color=color), flush=True)
            previous = trace
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
