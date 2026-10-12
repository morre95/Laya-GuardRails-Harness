"""Supervised fine-tuning of a Laya checkpoint with log loss against human labels.

Log loss is a strictly proper scoring rule, so the probabilities stay calibratable.
Only the decision logits are trained; the act head is frozen because LGH does not use it.
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import torch
from laya import Agent
from laya.common import QTYPES, build_sequence, collate_items, temp_bucket

from lgh.train.data import DatasetError, question_target

Items = list[dict[str, Any]]


@dataclass(frozen=True)
class TrainSettings:
    epochs: int = 4
    lr_encoder: float = 1e-5
    lr_head: float = 1e-4
    grad_accumulation: int = 8
    patience: int = 1
    seed: int = 0


def resolve_checkpoint_dir(model: str) -> str:
    """Local directory holding the checkpoint files (downloads a Hub id if needed)."""
    if os.path.isdir(model):
        return os.path.abspath(model)
    from huggingface_hub import snapshot_download

    return snapshot_download(model, token=os.environ.get("HF_TOKEN"))


def encode_row(agent: Agent, row: dict[str, Any]) -> Items:
    """One item per question, built exactly as Agent.system_one builds them at inference."""
    max_len = agent.cfg.get("max_len", 512)
    head_max_len = agent.cfg.get("head_max_len", 192)
    items = []
    for key, qdef in row["questions"].items():
        q = Agent._to_internal(qdef)
        ids, markers = build_sequence(agent.tok, row["state"], q, max_len, head_max_len)
        target = question_target(qdef, row["labels"][key])
        if len(markers) != len(target):
            raise DatasetError(f"question {key!r}: options exceed head_max_len={head_max_len}")
        items.append({"ids": ids, "markers": markers, "qtype": QTYPES[q["t"]], "target": target})
    return items


def _autocast_dtype(device: torch.device) -> torch.dtype | None:
    if device.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return None


def _forward(agent: Agent, items: Items) -> tuple[torch.Tensor, torch.Tensor]:
    batch = collate_items([items], agent.tok.pad_token_id)
    device = agent.device
    dtype = _autocast_dtype(device)
    with torch.autocast(device_type=device.type, dtype=dtype or torch.float32, enabled=dtype is not None):
        logits, _ = agent.model(
            batch["input_ids"].to(device),
            batch["attention_mask"].to(device),
            batch["marker_pos"].to(device),
            batch["marker_mask"].to(device),
            batch["qtype"].to(device),
        )
    return logits.float(), batch["target"].to(device)


def _log_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    # Padding options carry -1e4 logits and zero target, so they drop out of the sum.
    return -(target * torch.log_softmax(logits, -1)).sum(-1).mean()


@torch.no_grad()
def validation_loss(agent: Agent, encoded: list[Items]) -> float:
    agent.model.eval()
    total = sum(_log_loss(*_forward(agent, items)).item() for items in encoded)
    return total / len(encoded)


def _optimizer(agent: Agent, settings: TrainSettings) -> torch.optim.Optimizer:
    model = agent.model
    model.act_head.requires_grad_(False)
    encoder = [p for p in model.encoder.parameters() if p.requires_grad]
    encoder_ids = {id(p) for p in encoder}
    head = [p for p in model.parameters() if p.requires_grad and id(p) not in encoder_ids]
    return torch.optim.AdamW(
        [{"params": encoder, "lr": settings.lr_encoder}, {"params": head, "lr": settings.lr_head}]
    )


def _train_epoch(
    agent: Agent, encoded: list[Items], optimizer: torch.optim.Optimizer, settings: TrainSettings, rng: random.Random
) -> float:
    agent.model.train()
    order = list(range(len(encoded)))
    rng.shuffle(order)
    total = 0.0
    optimizer.zero_grad()
    for step, index in enumerate(order, start=1):
        loss = _log_loss(*_forward(agent, encoded[index]))
        (loss / settings.grad_accumulation).backward()
        total += loss.item()
        if step % settings.grad_accumulation == 0 or step == len(order):
            optimizer.step()
            optimizer.zero_grad()
    return total / len(order)


def train_model(
    agent: Agent,
    train: list[Items],
    val: list[Items],
    settings: TrainSettings,
    log: Callable[[str], None],
) -> list[dict[str, float]]:
    """Train in place, keep the weights with the lowest validation loss, return per-epoch history."""
    torch.manual_seed(settings.seed)
    rng = random.Random(settings.seed)
    optimizer = _optimizer(agent, settings)
    agent.model.encoder.gradient_checkpointing_enable()
    best_loss = validation_loss(agent, val)
    best_state = {k: v.detach().to("cpu", copy=True) for k, v in agent.model.state_dict().items()}
    history = [{"epoch": 0, "val_loss": best_loss}]
    log(f"epoch 0  val_loss={best_loss:.4f}")
    stale = 0
    for epoch in range(1, settings.epochs + 1):
        train_loss = _train_epoch(agent, train, optimizer, settings, rng)
        val_loss = validation_loss(agent, val)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        log(f"epoch {epoch}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}")
        if val_loss < best_loss:
            best_loss, stale = val_loss, 0
            best_state = {k: v.detach().to("cpu", copy=True) for k, v in agent.model.state_dict().items()}
        else:
            stale += 1
            if stale > settings.patience:
                log("validation loss stopped improving; stopping early")
                break
    agent.model.encoder.gradient_checkpointing_disable()
    agent.model.load_state_dict(best_state)
    agent.model.eval()
    return history


@torch.no_grad()
def temperature_samples(agent: Agent, encoded: list[Items]) -> list[tuple[str, list[float], list[float]]]:
    """(temp_bucket, raw logits, target) per question, for fitting inference temperatures."""
    agent.model.eval()
    samples = []
    for items in encoded:
        logits, _ = _forward(agent, items)
        for row, item in enumerate(items):
            k = len(item["markers"])
            samples.append((temp_bucket(item["qtype"], k), logits[row, :k].tolist(), item["target"]))
    return samples
