import json
import math

import pytest

from lgh.config.models import GuardrailConfig
from lgh.laya.client import state_payload
from lgh.laya.questions import load_questions
from lgh.state.builder import build_laya_state
from lgh.train.data import (
    MIN_TRAIN_SUPPORT,
    DatasetError,
    chronological_split,
    class_support,
    load_rows,
    question_target,
    support_warnings,
)
from lgh.train.evaluate import fit_bucket_temperatures, score_question
from tests.helpers import make_envelope

QUESTIONS = load_questions()
SAFE_LABELS = {
    "task_alignment": "aligned",
    "destructive_risk": 0.0,
    "sensitive_resource": 0.0,
    "external_impact": 0.0,
    "reversibility": "trivial",
    "verification_needed": 0.0,
    "handling": "allow",
}


def make_row(index: int, **labels) -> dict:
    state = state_payload(build_laya_state(make_envelope(command=f"pytest -k t{index}"), GuardrailConfig()))
    return {
        "trace_id": f"t{index}",
        "timestamp": f"2026-10-{index + 1:02d}T00:00:00.000Z",
        "state": state,
        "questions": QUESTIONS,
        "labels": {**SAFE_LABELS, **labels},
        "source": "human",
    }


def write_rows(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_choice_target_is_one_hot_in_criteria_order() -> None:
    assert question_target(QUESTIONS["handling"], "replan") == [0.0, 0.0, 1.0, 0.0]


def test_noul_target_is_false_true_pair() -> None:
    assert question_target(QUESTIONS["destructive_risk"], 0.2) == pytest.approx([0.8, 0.2])


def test_unknown_choice_label_is_rejected() -> None:
    with pytest.raises(DatasetError):
        question_target(QUESTIONS["handling"], "block")


def test_split_puts_newest_rows_in_validation() -> None:
    rows = [make_row(i) for i in (3, 0, 4, 1, 2)]
    train, val = chronological_split(rows, val_fraction=0.4)
    assert [r["trace_id"] for r in train] == ["t0", "t1", "t2"]
    assert [r["trace_id"] for r in val] == ["t3", "t4"]


def test_split_needs_two_rows() -> None:
    with pytest.raises(DatasetError):
        chronological_split([make_row(0)])


def test_support_counts_noul_at_half_as_true() -> None:
    support = class_support([make_row(0, destructive_risk=0.5), make_row(1)], QUESTIONS)
    assert support["destructive_risk"] == {"false": 1, "true": 1}
    assert support["handling"] == {"allow": 2, "verify": 0, "replan": 0, "escalate": 0}


def test_warnings_flag_thin_and_unmeasurable_classes() -> None:
    train = class_support([make_row(0, handling="replan")], QUESTIONS)
    val = class_support([make_row(1)], QUESTIONS)
    warnings = support_warnings(train, val)
    assert f"handling=replan: 1 training examples (< {MIN_TRAIN_SUPPORT}); expect it not to be learned" in warnings
    assert "handling=replan: no validation examples; its accuracy cannot be measured" in warnings


def test_load_rows_refuses_laya_labels(tmp_path) -> None:
    path = tmp_path / "ds.jsonl"
    write_rows(path, [{**make_row(0), "source": "laya"}])
    with pytest.raises(DatasetError, match="never train"):
        load_rows(path)


def test_load_rows_requires_timestamp(tmp_path) -> None:
    path = tmp_path / "ds.jsonl"
    row = make_row(0)
    del row["timestamp"]
    write_rows(path, [row])
    with pytest.raises(DatasetError, match="re-run `lgh export-dataset`"):
        load_rows(path)


def test_score_question_choice_accuracy_and_recall() -> None:
    qdef = QUESTIONS["handling"]
    answers = [
        {"probabilities": {"allow": 0.7, "verify": 0.2, "replan": 0.05, "escalate": 0.05}},
        {"probabilities": {"allow": 0.6, "verify": 0.3, "replan": 0.05, "escalate": 0.05}},
    ]
    result = score_question(answers, ["allow", "verify"], qdef)
    assert result["accuracy"] == 0.5
    assert result["recall"]["verify"] == {"support": 1, "correct": 0}
    assert result["log_loss"] == pytest.approx((-math.log(0.7) - math.log(0.3)) / 2)


def test_score_question_noul_uses_soft_targets() -> None:
    result = score_question([{"noul": 0.2}], [0.2], QUESTIONS["destructive_risk"])
    assert result["accuracy"] == 1.0
    assert result["brier"] == pytest.approx(0.0)


def test_temperature_fit_softens_overconfident_logits() -> None:
    # Logits say 99.99% but the outcome is a coin flip: the fit must flatten them.
    samples = [("noul:2", [0.0, 9.0], [0.0, 1.0]), ("noul:2", [0.0, 9.0], [1.0, 0.0])] * 10
    assert fit_bucket_temperatures(samples)["noul:2"] == 5.0


@pytest.mark.laya
def test_train_smoke_saves_loadable_checkpoint(tmp_path) -> None:
    pytest.importorskip("laya")
    huggingface_hub = pytest.importorskip("huggingface_hub")
    from huggingface_hub.errors import LocalEntryNotFoundError

    from lgh.daemon.server import MODEL_ID
    from lgh.train.loop import TrainSettings
    from lgh.train.runner import run_training

    try:
        huggingface_hub.snapshot_download(MODEL_ID, local_files_only=True)
    except LocalEntryNotFoundError:
        pytest.skip(f"{MODEL_ID} is not in the local Hugging Face cache")
    import torch

    dataset = tmp_path / "ds.jsonl"
    write_rows(dataset, [make_row(0), make_row(1, handling="verify"), make_row(2), make_row(3)])
    output = tmp_path / "model"
    report = run_training(
        dataset,
        output,
        base=MODEL_ID,
        device="cuda" if torch.cuda.is_available() else "cpu",
        settings=TrainSettings(epochs=1, grad_accumulation=2),
        log=lambda _: None,
    )
    assert (output / "model.safetensors").is_file()
    assert json.loads((output / "rl_agent_config.json").read_text())["lgh_training"]["base"] == MODEL_ID
    assert set(report["metrics"]["fine_tuned"]) == set(QUESTIONS)
