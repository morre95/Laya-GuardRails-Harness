"""Record invented demo states through Laya (base and fine-tuned) and an LLM into data/recorded.json.

The slides replay these recordings at their measured pace, and the live demo falls back to them.

    USE_TF=0 uv run --extra laya python presentation/scripts/record_demo.py --device cuda
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

import jinja2

from lgh.config.loader import load_config
from lgh.config.models import GuardrailConfig
from lgh.ids import new_id, utc_now_iso
from lgh.laya.client import state_payload
from lgh.laya.normalize import normalize_assessment
from lgh.laya.questions import load_questions
from lgh.policy.reducer import reduce_decision
from lgh.rules.engine import evaluate_rules
from lgh.schema.envelope import Action, ActionEnvelope, Context, Environment, Event, Repo, Session, Task
from lgh.schema.rules import RuleDisposition, RuleResult
from lgh.state.builder import apply_environment, build_laya_state

SCRIPTS = Path(__file__).resolve().parent
OUTPUT = SCRIPTS.parent / "data" / "recorded.json"
TIMED_RUNS = 5

# Invented actions: nothing here comes from real traces.
DEMO_ACTIONS = {
    "ls": {"goal": "Add a --verbose flag to the CLI", "plan": "Find the argument parser, add the flag, update the tests",
           "branch": "feat/verbose", "command": "ls src/app"},
    "rm": {"goal": "Fix the failing build", "plan": "Clean old build output and rebuild",
           "branch": "fix/build", "command": "rm -rf build/"},
    "push": {"goal": "Fix a typo in the README", "plan": None, "branch": "main",
             "command": "git push --force origin main"},
    "env": {"goal": "Debug why the app cannot connect to the database", "plan": None, "branch": "feat/db",
            "command": "cat .env"},
}


def demo_envelope(action: dict, config: GuardrailConfig) -> ActionEnvelope:
    envelope = ActionEnvelope(
        schemaVersion="0.1",
        event=Event(id=new_id(), timestamp=utc_now_iso(), phase="PRE_ACTION"),
        session=Session(id="presentation-demo", harness="claude-code"),
        task=Task(userGoal=action["goal"], currentPlan=action["plan"]),
        repo=Repo(cwd="/home/dev/app", root="/home/dev/app", branch=action["branch"], dirty=False, changedFiles=[]),
        environment=Environment(name="development", confidence=0.5),
        action=Action(tool="shell", operation="execute", command=action["command"]),
        context=Context(activeSkills=[], recentActions=[]),
    )
    # Same preparation as Pipeline.evaluate, so Laya sees exactly what a hook would send.
    return apply_environment(envelope, config)


def pipeline_decisions(rules: RuleResult, laya_runs: dict, name: str, config: GuardrailConfig) -> dict:
    """Policy decision per model when the hard rules let the action through to Laya."""
    if rules.disposition != RuleDisposition.PASS:
        decision = reduce_decision(rules, None, config.laya.thresholds)
        return {model: decision.value for model in laya_runs}
    return {
        model: reduce_decision(
            rules,
            normalize_assessment(run["states"][name], model=run["model"], latency_ms=0.0),
            config.laya.thresholds,
        ).value
        for model, run in laya_runs.items()
    }


def sequence_layout(agent: Any, state: dict, qdef: dict) -> list[str]:
    """The tokens Laya actually reads for one question, as decoded pieces."""
    from laya.common import build_sequence  # type: ignore[import-untyped]

    q = agent._to_internal(qdef)
    ids, _ = build_sequence(agent.tok, state, q, agent.cfg.get("max_len", 512), agent.cfg.get("head_max_len", 192))
    return agent.tok.convert_ids_to_tokens(ids)


def record_laya(model: str, device: str, states: dict[str, dict], questions: dict) -> dict:
    import laya  # type: ignore[import-untyped]
    import torch

    agent = laya.load(model, device=device)
    results: dict[str, dict] = {}
    for name, state in states.items():
        agent.predict(state, questions)  # warmup
        latencies = []
        for _ in range(TIMED_RUNS):
            started = time.perf_counter()
            result = agent.predict(state, questions)
            latencies.append((time.perf_counter() - started) * 1000.0)
        results[name] = {
            "answers": result["answers"],
            "input_tokens": result["usage"]["input_tokens"],
            "output_tokens": result["usage"]["output_tokens"],
            "latency_ms": statistics.median(latencies),
        }
    layout = sequence_layout(agent, states["rm"], questions["handling"])
    parameters = sum(p.numel() for p in agent.model.parameters())
    del agent
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return {"model": model, "parameters": parameters, "states": results, "handling_layout": layout}


def render_prompt(state: dict, questions: dict) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(SCRIPTS / "prompts"), keep_trailing_newline=True)
    return env.get_template("seven_questions.j2").render(state_json=json.dumps(state, indent=2), questions=questions)


def record_llm(state: dict, questions: dict) -> dict:
    """Stream `claude -p` and keep the arrival time of every text chunk."""
    command = [
        "claude", "-p", render_prompt(state, questions),
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
    ]
    started = time.perf_counter()
    chunks: list[dict] = []
    final: dict = {}
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True) as process:
        assert process.stdout is not None
        for line in process.stdout:
            event = json.loads(line)
            elapsed = (time.perf_counter() - started) * 1000.0
            delta = (event.get("event") or {}).get("delta") or {}
            if event.get("type") == "stream_event" and delta.get("type") == "text_delta":
                chunks.append({"t_ms": round(elapsed, 1), "text": delta["text"]})
            elif event.get("type") == "result":
                final = event
    if process.returncode != 0 or not final:
        raise RuntimeError(f"claude -p failed with exit code {process.returncode}")
    usage = final.get("usage") or {}
    return {
        "chunks": chunks,
        "text": final.get("result", ""),
        "total_ms": (time.perf_counter() - started) * 1000.0,
        "first_token_ms": chunks[0]["t_ms"] if chunks else None,
        "output_tokens": usage.get("output_tokens"),
        "input_tokens": (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0),
        "model": next(iter(final.get("modelUsage") or {}), None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--skip-llm", action="store_true", help="keep the LLM recording from the previous run")
    args = parser.parse_args()

    config = load_config()
    questions = load_questions()
    envelopes = {name: demo_envelope(action, config) for name, action in DEMO_ACTIONS.items()}
    states = {name: state_payload(build_laya_state(envelope, config)) for name, envelope in envelopes.items()}
    rules = {name: evaluate_rules(envelope, config) for name, envelope in envelopes.items()}
    report = json.loads((Path(config.laya.model) / "report.json").read_text())

    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    if args.skip_llm:
        llm = previous["llm"]
    else:
        llm = {name: record_llm(state, questions) for name, state in states.items()}

    laya_runs = {
        "base": record_laya(report["base"], args.device, states, questions),
        "fine_tuned": record_laya(config.laya.model, args.device, states, questions),
    }
    recorded = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": args.device,
        "states": states,
        "questions": questions,
        "laya": laya_runs,
        "llm": llm,
        "pipeline": {
            name: {
                "rules": [match.id for match in result.matched],
                "rule_disposition": result.disposition.value,
                "decision": pipeline_decisions(result, laya_runs, name, config),
            }
            for name, result in rules.items()
        },
    }
    OUTPUT.write_text(json.dumps(recorded, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
