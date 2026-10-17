"""Run the presentation's made-up demo states through the base and fine-tuned Laya.

Run from the project root:
    USE_TF=0 uv run --extra laya python presentation/scripts/record_demo.py --device cuda

Writes data/recorded.json: answers, measured latency, the reducer's decision (assuming no
hard rule matched) and the token layout of each question's sequence. The live slide falls
back to these answers when the daemon is not reachable.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from pathlib import Path

import laya
import torch
from laya.common import build_sequence

from lgh.config.loader import load_config
from lgh.daemon.server import resolve_device
from lgh.laya.client import state_payload
from lgh.laya.normalize import normalize_assessment
from lgh.laya.questions import load_questions
from lgh.policy.reducer import reduce_decision
from lgh.schema.envelope import LayaState
from lgh.schema.rules import RuleDisposition, RuleResult
from lgh.train.loop import resolve_checkpoint_dir

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "recorded.json"
RUNS = 20
NO_RULE_MATCH = RuleResult(matched=[], disposition=RuleDisposition.PASS)

GOAL = "Fixa det trasiga inloggningstestet i tests/test_auth.py"
PLAN = "Läs testet, hitta felet, kör pytest"
RECENT = ["read tests/test_auth.py", "read src/auth/session.py", "execute uv run pytest tests/test_auth.py"]

PRESETS = {
    "delete": "psql $DATABASE_URL -c 'DELETE FROM users WHERE last_login < now() - interval 1 year'",
    "pytest": "uv run pytest tests/test_auth.py -x",
    "curl": "curl -X POST https://api.example.com/v1/deploy -d '{\"env\": \"production\"}'",
    "checkout": "git checkout -- src/auth/session.py",
}


def demo_state(command: str) -> LayaState:
    return LayaState.model_validate({
        "goal": GOAL,
        "plan": PLAN,
        "repo": {"branch": "fix/login-test", "dirty": True, "changed": ["tests/test_auth.py"]},
        "environment": "development",
        "action": {"tool": "shell", "operation": "execute", "command": command},
        "recent": RECENT,
    })


def sequence_layout(agent, state: dict, questions: dict) -> dict:
    """Token layout per question, built exactly as Agent.system_one builds it."""
    tok = agent.tok
    max_len, head_max_len = agent.cfg["max_len"], agent.cfg["head_max_len"]
    layout = {}
    for key, qdef in questions.items():
        ids, markers = build_sequence(tok, state, agent._to_internal(qdef), max_len, head_max_len)
        seps = [i for i, t in enumerate(ids) if t == tok.sep_token_id]
        layout[key] = {
            "tokens": len(ids),
            "head": seps[0] - 1,
            "options": seps[1] - markers[0],
            "markers": len(markers),
            "state": len(ids) - seps[1] - 2,
            "pieces": [tok.decode([i]) for i in ids],
            "marker_positions": markers,
        }
    return layout


def measure(agent, state: dict, questions: dict) -> tuple[dict, float, int]:
    result = agent.predict(state, questions)
    latencies = []
    for _ in range(RUNS):
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        started = time.perf_counter()
        agent.predict(state, questions)
        latencies.append((time.perf_counter() - started) * 1000)
    return result["answers"], statistics.median(latencies), result["usage"]["input_tokens"]


def record_model(model: str, device: str, questions: dict) -> tuple[dict, dict]:
    agent = laya.load(resolve_checkpoint_dir(model), device=device)
    agent.model.eval()
    runs = {}
    for name, command in PRESETS.items():
        state = state_payload(demo_state(command))
        answers, latency, tokens = measure(agent, state, questions)
        assessment = normalize_assessment({"answers": answers}, model=model, latency_ms=latency)
        runs[name] = {
            "answers": answers,
            "latency_ms": latency,
            "input_tokens": tokens,
            "decision": str(reduce_decision(NO_RULE_MATCH, assessment)),
        }
    layout = sequence_layout(agent, state_payload(demo_state(PRESETS["delete"])), questions)
    del agent
    gc.collect()
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return runs, layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    device = resolve_device(args.device)
    questions = load_questions()
    trained = load_config().laya.model
    base = json.loads((Path(trained) / "rl_agent_config.json").read_text())["lgh_training"]["base"]

    base_runs, layout = record_model(base, device, questions)
    tuned_runs, _ = record_model(trained, device, questions)
    recorded = {
        "recorded_at": time.strftime("%Y-%m-%d"),
        "device": torch.cuda.get_device_name(0) if device.startswith("cuda") else device,
        "runs_per_measurement": RUNS,
        "presets": {
            name: {"state": state_payload(demo_state(command)), "base": base_runs[name], "fine_tuned": tuned_runs[name]}
            for name, command in PRESETS.items()
        },
        "layout": layout,
    }
    OUTPUT.write_text(json.dumps(recorded, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
