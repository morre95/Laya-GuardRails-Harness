import json

import pytest

from lgh.cli import main
from lgh.eval.compare import (
    audit_dataset,
    compare_predictions,
    detailed_metrics,
    file_hash,
    read_dataset,
    run_comparison,
)
from lgh.train.data import DatasetError
from tests.unit.test_train import QUESTIONS, make_row, write_rows


def prediction(row, **overrides):
    answers = {}
    for key, qdef in QUESTIONS.items():
        label = overrides.get(key, row["labels"][key])
        if qdef["type"] == "choice":
            answers[key] = {"probabilities": {option: float(option == label) for option in qdef["criteria"]}}
        else:
            answers[key] = {"noul": float(label)}
    return answers


def test_audit_checks_both_id_and_state_even_when_questions_change(tmp_path):
    path = tmp_path / "training.jsonl"
    row = make_row(0)
    write_rows(path, [row])
    same_id = {**make_row(1), "trace_id": row["trace_id"]}
    same_state = {**row, "trace_id": "renamed", "questions": {}}
    audit = audit_dataset([same_id, same_state], path, {"dataset_sha256": file_hash(path)})
    assert audit["status"] == "reused"
    assert audit["overlap_ids"] == ["t0"]
    assert audit["overlap_states"] == ["renamed"]


def test_audit_requires_the_original_training_export(tmp_path):
    path = tmp_path / "training.jsonl"
    write_rows(path, [make_row(0)])
    with pytest.raises(DatasetError, match="dataset_sha256"):
        audit_dataset([make_row(1)], path, {"dataset_sha256": "wrong"})
    assert audit_dataset([make_row(1)], path, {})["status"] == "unverified_training_dataset"
    assert audit_dataset([make_row(1)], None, {})["status"] == "unknown"


def test_audit_includes_separate_validation_and_calibration(tmp_path):
    train, cal = tmp_path / 'train.jsonl', tmp_path / 'cal.jsonl'
    write_rows(train, [make_row(0)])
    write_rows(cal, [make_row(1)])
    metadata = {'dataset_sha256': file_hash(train), 'datasets': {
        'calibration': {'path': str(cal), 'sha256': file_hash(cal)}}}
    assert audit_dataset([make_row(1)], train, metadata)['status'] == 'reused'
    cal.unlink()
    with pytest.raises(DatasetError, match='calibration'):
        audit_dataset([make_row(2)], train, metadata)


def test_audit_rejects_family_overlap(tmp_path):
    train = tmp_path / 'train.jsonl'
    write_rows(train, [{**make_row(0), 'group_id': 'family'}])
    test = {**make_row(1), 'group_id': 'family'}
    result = audit_dataset([test], train, {'dataset_sha256': file_hash(train)})
    assert result['status'] == 'reused'


def test_dataset_requires_independent_complete_labels(tmp_path):
    path = tmp_path / "test.jsonl"
    row = {**make_row(0), "source": "laya"}
    write_rows(path, [row])
    with pytest.raises(DatasetError, match="reference labels"):
        read_dataset(path)
    blind = read_dataset(path, unlabeled=True)
    assert "labels" not in blind[0]
    assert "source" not in blind[0]
    write_rows(path, [make_row(0, destructive_risk=float("nan"))])
    with pytest.raises(DatasetError, match="invalid label"):
        read_dataset(path)


def test_row_context_exclusions_apply_without_an_override_file(tmp_path):
    path = tmp_path / 'test.jsonl'
    write_rows(path, [{**make_row(0), 'review_status': 'insufficient_context'}, make_row(1)])
    assert [r['trace_id'] for r in read_dataset(path)] == ['t1']


@pytest.mark.parametrize('unlabeled', [False, True])
def test_only_complete_valid_override_restores_row_context(tmp_path, unlabeled):
    path, labels = tmp_path / 'test.jsonl', tmp_path / 'labels.jsonl'
    row = {**make_row(0), 'review_status': 'insufficient_context'}
    write_rows(path, [row, make_row(1)])
    write_rows(labels, [{'trace_id': 't0', 'source': 'human', 'handling': 'allow'}])
    assert [r['trace_id'] for r in read_dataset(path, labels=labels, unlabeled=unlabeled)] == ['t1']
    write_rows(labels, [{'trace_id': 't0', 'source': 'human', **row['labels']}])
    assert [r['trace_id'] for r in read_dataset(path, labels=labels, unlabeled=unlabeled)] == ['t0', 't1']


def test_dataset_rejects_duplicate_traces_and_loads_latest_reference(tmp_path):
    path = tmp_path / "test.jsonl"
    row = make_row(0)
    write_rows(path, [row, row])
    with pytest.raises(DatasetError, match="duplicate trace_id"):
        read_dataset(path)
    write_rows(path, [{k: v for k, v in row.items() if k not in ("labels", "source")}])
    labels = tmp_path / "labels.jsonl"
    write_rows(labels, [
        {"trace_id": "t0", "source": "human", **row["labels"]},
        {"trace_id": "t0", "source": "human", **row["labels"], "handling": "verify"},
    ])
    assert read_dataset(path, labels=labels)[0]["labels"]["handling"] == "verify"


def test_metrics_expose_missed_risks_and_unnecessary_interventions():
    rows = [make_row(0), make_row(1, handling="verify"), make_row(2, handling="replan")]
    predictions = [prediction(rows[0], handling="verify"), prediction(rows[1], handling="allow"), prediction(rows[2])]
    metrics = detailed_metrics(predictions, rows)
    intervention = metrics["handling"]["intervention"]
    assert intervention == {
        "needed": 2, "detected": 1, "missed": 1, "unnecessary": 1, "safe": 1,
        "recall": 0.5, "unnecessary_rate": 1.0,
    }
    assert metrics["handling"]["classes"]["escalate"]["recall"] is None
    assert metrics["handling"]["majority_baseline_accuracy"] == pytest.approx(1 / 3)
    assert metrics["handling"]["confusion_matrix"]["verify"]["allow"] == 1


def test_paired_results_identify_regressions_not_only_disagreements():
    rows = [make_row(0), make_row(1, handling="verify")]
    base = [prediction(rows[0], handling="verify"), prediction(rows[1])]
    tuned = [prediction(rows[0]), prediction(rows[1], handling="allow")]
    paired, changes = compare_predictions(base, tuned, rows, False)
    assert paired["handling"] == {"disagreements": 2, "improved": 1, "regressed": 1}
    assert changes[1]["changes"]["handling"]["reference"] == "verify"
    blind, _ = compare_predictions(base, tuned, rows, True)
    assert blind["handling"] == {"disagreements": 2}


@pytest.mark.parametrize("unlabeled", [False, True])
def test_comparison_freezes_inputs_and_never_refits_models(tmp_path, monkeypatch, unlabeled):
    from lgh.eval import compare

    training = tmp_path / "training.jsonl"
    dataset = tmp_path / "test.jsonl"
    write_rows(training, [make_row(0)])
    row = make_row(1, handling="verify")
    write_rows(dataset, [row])
    trained = tmp_path / "trained"
    trained.mkdir()
    (trained / "rl_agent_config.json").write_text(json.dumps({"lgh_training": {
        "base": "stock", "dataset_sha256": file_hash(training),
    }}))
    calls = []

    class Agent:
        def __init__(self, model):
            self.name = model

        def predict(self, state, questions):
            calls.append((self.name, state, questions))
            return {"answers": prediction(row, handling="allow" if self.name == "stock" else "verify")}

    monkeypatch.setattr(compare, "_load_agent", lambda model, device: (Agent(model), {"requested": model}))
    output = tmp_path / "comparison"
    report = run_comparison(dataset, trained, output, training_dataset=training, unlabeled=unlabeled)
    assert report["audit"]["status"] == "no_exact_overlap"
    assert len(calls) == 4  # One warmup and one measured prediction per checkpoint.
    assert all(call[1:] == (row["state"], row["questions"]) for call in calls)
    assert report["paired"]["handling"]["disagreements"] == 1
    if unlabeled:
        assert report["metrics"] is None
        assert "labels" not in json.loads((output / "dataset.jsonl").read_text())
    else:
        assert report["metrics"]["fine_tuned"]["handling"]["accuracy"] == 1
    assert json.loads((output / "report.json").read_text()) == report
    assert (output / "report.md").is_file()
    with pytest.raises(DatasetError, match="already exists"):
        run_comparison(dataset, trained, output, training_dataset=training)


def test_cli_rejects_reused_dataset_before_loading_models(tmp_path, capsys):
    path = tmp_path / "dataset.jsonl"
    write_rows(path, [make_row(0)])
    trained = tmp_path / "trained"
    trained.mkdir()
    (trained / "rl_agent_config.json").write_text(json.dumps({"lgh_training": {"dataset_sha256": file_hash(path)}}))
    output = tmp_path / "output"
    assert main(["compare", "--dataset", str(path), "--trained", str(trained),
                 "--training-dataset", str(path), "--output", str(output)]) == 1
    assert "data audit: reused" in capsys.readouterr().err
    assert not output.exists()


def test_comparison_omits_cases_marked_insufficient_context(tmp_path):
    path = tmp_path / 'test.jsonl'
    labels = tmp_path / 'labels.jsonl'
    write_rows(path, [make_row(0), make_row(1)])
    write_rows(labels, [{'trace_id': 't0', 'source': 'human',
                         'review_status': 'insufficient_context', 'reason': 'Missing goal'}])
    assert [row['trace_id'] for row in read_dataset(path, labels=labels)] == ['t1']


def test_comparison_reports_when_all_cases_are_excluded(tmp_path):
    path = tmp_path / 'test.jsonl'
    labels = tmp_path / 'labels.jsonl'
    write_rows(path, [make_row(0)])
    write_rows(labels, [{'trace_id': 't0', 'source': 'human',
                         'review_status': 'insufficient_context', 'reason': 'Missing goal'}])
    with pytest.raises(DatasetError, match='empty after context exclusions'):
        read_dataset(path, labels=labels)
