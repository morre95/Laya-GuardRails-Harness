"""`lgh train`: dataset → fine-tuned checkpoint + report comparing it with the base model."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lgh.ids import utc_now_iso
from lgh.train.data import DatasetError, assert_disjoint, chronological_split, class_support, load_rows, support_warnings
from lgh.train.evaluate import fit_bucket_temperatures, score_predictions

if TYPE_CHECKING:
    from lgh.train.loop import TrainSettings

CALIBRATION_NOTE = (
    "Temperatures are fitted on the validation split, so fine_tuned calibration metrics are optimistic."
)


def _predict(agent: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [agent.predict(row["state"], row["questions"])["answers"] for row in rows]


def run_training(
    dataset: Path,
    output: Path,
    base: str,
    device: str,
    settings: TrainSettings,
    log: Callable[[str], None] = print,
    *,
    validation: Path | None = None,
    calibration: Path | None = None,
) -> dict[str, Any]:
    import laya

    from lgh.daemon.server import resolve_device
    from lgh.eval.compare import file_hash
    from lgh.train.checkpoint import save_checkpoint, verify_checkpoint
    from lgh.train.loop import encode_row, resolve_checkpoint_dir, temperature_samples, train_model

    if output.exists():
        raise DatasetError(f'{output} already exists; pick a new output directory')
    if calibration is not None and validation is None:
        raise DatasetError('an explicit calibration dataset requires explicit validation')
    paths = {name: path for name, path in [('train', dataset), ('validation', validation),
                                         ('calibration', calibration)] if path is not None}
    datasets = {name: {'path': str(path.resolve()), 'sha256': file_hash(path)} for name, path in paths.items()}
    rows = load_rows(dataset)
    questions = rows[0]["questions"]
    train_rows, val_rows = (rows, load_rows(validation)) if validation else chronological_split(rows)
    cal_rows = load_rows(calibration) if calibration else val_rows
    partitions = {'train': train_rows, 'validation': val_rows}
    if calibration:
        partitions['calibration'] = cal_rows
    assert_disjoint(partitions)
    support = {"train": class_support(train_rows, questions), "val": class_support(val_rows, questions)}
    warnings = support_warnings(support["train"], support["val"])
    log(f"{len(train_rows)} train, {len(val_rows)} validation, {len(cal_rows)} calibration"
        + (' (separate)' if calibration else ' (reuses validation)'))
    for warning in warnings:
        log(f"warning: {warning}")

    base_dir = resolve_checkpoint_dir(base)
    base_identity = {name: file_hash(Path(base_dir) / name) for name in ('model.safetensors', 'rl_agent_config.json')}
    agent = laya.load(base_dir, device=resolve_device(device))
    if str(device).startswith(('cuda', 'gpu')) and agent.device.type != 'cuda':
        raise RuntimeError('Laya fell back from requested CUDA; training aborted')
    log(f"loaded {base} on {agent.device}")
    log("scoring base model on validation")
    base_metrics = score_predictions(_predict(agent, val_rows), val_rows, questions)

    train_items = [encode_row(agent, row) for row in train_rows]
    val_items = [encode_row(agent, row) for row in val_rows]
    history = train_model(agent, train_items, val_items, settings, log)

    cal_items = [encode_row(agent, row) for row in cal_rows] if calibration else val_items
    temperatures = fit_bucket_temperatures(temperature_samples(agent, cal_items))
    agent.temperature_by_options = {**agent.temperature_by_options, **temperatures}
    log("scoring fine-tuned model on validation")
    tuned_metrics = score_predictions(_predict(agent, val_rows), val_rows, questions)

    # Refuse to attribute training to inputs or base weights changed during the run.
    for name, path in paths.items():
        if file_hash(path) != datasets[name]['sha256']:
            raise DatasetError(f'{name} dataset changed during training')
    if any(file_hash(Path(base_dir) / name) != digest for name, digest in base_identity.items()):
        raise DatasetError('base checkpoint changed during training')

    metadata = {
        "base": base,
        "trained_at": utc_now_iso(),
        "dataset_sha256": datasets['train']['sha256'],
        "base_identity": base_identity,
        "rows": {"train": len(train_rows), "val": len(val_rows)},
        "settings": asdict(settings),
        "datasets": datasets,
    }
    save_checkpoint(agent, base_dir, output, temperatures, metadata)
    log(f"verifying {output} loads with laya")
    verify_checkpoint(output)

    report = {
        **metadata,
        "checkpoint": str(output.resolve()),
        "support": support,
        "warnings": warnings,
        "history": history,
        "temperatures": temperatures,
        "metrics": {"base": base_metrics, "fine_tuned": tuned_metrics},
        "notes": [
            'Validation selects weights; calibration uses a disjoint dataset. These are development metrics, not final test evidence.'
            if calibration else CALIBRATION_NOTE
        ],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def summary_table(report: dict[str, Any]) -> str:
    lines = [f"{'question':<22}{'accuracy':>20}{'log loss':>20}{'brier':>20}", "-" * 82]
    base, tuned = report["metrics"]["base"], report["metrics"]["fine_tuned"]
    for key in base:
        cells = [f"{base[key][m]:.3f} → {tuned[key][m]:.3f}" for m in ("accuracy", "log_loss", "brier")]
        lines.append(f"{key:<22}" + "".join(f"{cell:>20}" for cell in cells))
    return "\n".join(lines)
