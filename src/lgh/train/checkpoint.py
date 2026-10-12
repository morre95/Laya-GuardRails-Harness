"""Save a fine-tuned model in Laya's checkpoint layout so `laya.load(path)` loads it unchanged."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from laya import Agent
from safetensors.torch import save_file

_COPIED_FROM_BASE = ("tokenizer", "encoder", "config.json")


def save_checkpoint(
    agent: Agent,
    base_dir: str,
    output: Path,
    temperatures: dict[str, float],
    metadata: dict[str, Any],
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    for name in _COPIED_FROM_BASE:
        source = Path(base_dir) / name
        if source.is_dir():
            shutil.copytree(source, output / name)
        elif source.is_file():
            shutil.copy2(source, output / name)
    weights = {k: v.detach().cpu().contiguous() for k, v in agent.model.state_dict().items()}
    save_file(weights, str(output / "model.safetensors"))
    cfg = dict(agent.cfg)
    cfg["temperature_by_options"] = {**cfg.get("temperature_by_options", {}), **temperatures}
    cfg["fine_tuned"] = True
    cfg["lgh_training"] = metadata
    (output / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def verify_checkpoint(output: Path) -> None:
    """Load the saved checkpoint the way the daemon will; raises if laya rejects it."""
    Agent(str(output.resolve()), device="cpu")
