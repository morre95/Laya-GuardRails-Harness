import json

import pytest

from lgh.eval.compare_backends import collect_backend, combine_runs
from lgh.train.data import DatasetError
from tests.unit.test_backend_contract import answers, case, experiment, write_inputs


class FakeBackend:
    calls = []
    fail_on = None

    def __init__(self, spec, **kwargs):
        self.spec = spec

    def identity(self):
        return {'observed': {'model': self.spec.model}, 'declared': self.spec.model_dump(mode='json')}

    def predict(self, state, questions):
        self.calls.append(state)
        if self.fail_on and self.fail_on in state['goal']:
            raise DatasetError('simulated endpoint failure')
        row = {'questions': questions}
        return {'answers': answers(row), 'client_latency_ms': 10, 'server_latency_ms': 6,
                'usage': {}, 'prefix_cache_hit': None}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    FakeBackend.calls = []
    FakeBackend.fail_on = None
    monkeypatch.setattr('lgh.eval.compare_backends.HttpBackend', FakeBackend)
    exp = experiment()
    row, side = case(exp)
    paths = write_inputs(tmp_path, [row], [side])
    exp_path = tmp_path/'experiment.json'
    exp_path.write_text(exp.model_dump_json(indent=2))
    return exp_path, paths


def run(tmp_path, inputs, name='laya_current', **kwargs):
    exp, (dataset, replay) = inputs
    output = tmp_path/name
    collect_backend(dataset, replay, exp, name, output, allow_overlap=True, **kwargs)
    return output


def test_collection_freezes_inputs_replays_and_separates_samples(tmp_path, inputs):
    output = run(tmp_path, inputs)
    manifest = json.loads((output/'manifest.json').read_text())
    assert manifest['status'] == 'complete'
    assert manifest['backend'] == 'laya_current'
    assert manifest['timing']['repetitions'] == 3
    predictions = [json.loads(s) for s in (output/'predictions.jsonl').read_text().splitlines()]
    assert len(predictions) == 3
    assert predictions[0]['condition'] == 'first_observed'
    assert [p['condition'] for p in predictions[1:]] == ['repeated_request'] * 2
    assert len(FakeBackend.calls) == 4  # Disjoint warmup is excluded.
    states = [s['goal'] for s in FakeBackend.calls]
    assert states[0] != states[1]
    decisions = [json.loads(s) for s in (output/'decisions.jsonl').read_text().splitlines()]
    assert all(d['final_decision'] == 'ALLOW' and not d['executed'] for d in decisions)
    assert (output/'experiment.json').is_file()
    with pytest.raises(DatasetError): run(tmp_path, inputs)


def test_audit_rejects_unknown_training_before_calling_endpoint(tmp_path, inputs):
    exp, (dataset, replay) = inputs
    with pytest.raises(DatasetError, match='audit'):
        collect_backend(dataset, replay, exp, 'kev', tmp_path/'blocked')
    assert FakeBackend.calls == []
    assert not (tmp_path/'blocked').exists()


def test_endpoint_failure_leaves_explicit_incomplete_manifest(tmp_path, inputs):
    FakeBackend.fail_on = 'Do a thing'
    with pytest.raises(DatasetError): run(tmp_path, inputs)
    manifest = json.loads((tmp_path/'laya_current'/'manifest.json').read_text())
    assert manifest['status'] == 'incomplete'
    assert 'report.md' not in {p.name for p in (tmp_path/'laya_current').iterdir()}


def test_combine_requires_complete_distinct_compatible_backend_passes(tmp_path, inputs):
    current = run(tmp_path, inputs)
    kev = run(tmp_path, inputs, 'kev')
    released = run(tmp_path, inputs, 'laya_released')
    with pytest.raises(DatasetError): combine_runs([current, kev], tmp_path/'missing')
    with pytest.raises(DatasetError): combine_runs([current, current, kev], tmp_path/'duplicate')
    # Full combine implemented with report slice; complete passes must retain hashes.
    manifest = json.loads((kev/'manifest.json').read_text())
    assert manifest['dataset_sha256'] == json.loads((current/'manifest.json').read_text())['dataset_sha256']


def test_cli_help_and_collection_error_are_reviewable(tmp_path, capsys):
    from lgh.cli import main
    with pytest.raises(SystemExit) as exit:
        main(['compare-backends','--help'])
    assert exit.value.code == 0
    assert '--backend' in capsys.readouterr().out
    assert main(['compare-backends','--dataset', str(tmp_path/'absent'), '--output', str(tmp_path/'out')]) == 1


def test_hard_rule_path_timing_does_not_include_quality_model_request(tmp_path, inputs):
    exp_path, _ = inputs
    exp = experiment()
    row, side = case(exp, command='rm -rf /', requires=True)
    paths = write_inputs(tmp_path, [row], [side])
    output = run(tmp_path, (exp_path, paths))
    decision = json.loads((output/'decisions.jsonl').read_text().splitlines()[0])
    assert decision['model_dependent'] is False
    assert decision['accounted_harness_ms'] == decision['replay_latency_ms']
    assert len(FakeBackend.calls) == 4  # Raw quality inference still occurred.


def test_passes_with_different_frozen_inputs_cannot_be_combined(tmp_path, inputs):
    current = run(tmp_path, inputs)
    exp_path, _ = inputs
    exp = experiment()
    row, side = case(exp, command='echo different')
    changed = write_inputs(tmp_path, [row], [side])
    kev = run(tmp_path, (exp_path, changed), 'kev')
    released = run(tmp_path, (exp_path, changed), 'laya_released')
    with pytest.raises(DatasetError, match='incompatible'):
        combine_runs([current, kev, released], tmp_path/'bad-combine')


def test_wrong_original_training_export_is_rejected_even_in_exploratory_mode(tmp_path, inputs):
    from lgh.eval.compare import file_hash
    exp_path, (dataset, replay) = inputs
    model = tmp_path/'local-checkpoint'
    model.mkdir()
    (model/'model.safetensors').write_bytes(b'weights')
    (model/'rl_agent_config.json').write_text(json.dumps({'lgh_training':{'dataset_sha256':'f'*64}}))
    raw = json.loads(exp_path.read_text())
    raw['config']['laya']['model'] = str(model)
    raw['backends']['laya_current'].update(model=str(model), provenance='local_finetuned',
                                          revision=file_hash(model/'model.safetensors'),
                                          training_dataset=str(dataset))
    exp_path.write_text(json.dumps(raw))
    # Rebind only the replay configuration; it still represents the same case.
    from lgh.eval.backend_contract import Experiment, rule_config_hash
    binding = rule_config_hash(Experiment.model_validate(raw).config)
    side = json.loads(replay.read_text())
    side['rule_config_sha256'] = binding
    replay.write_text(json.dumps(side)+'\n')
    with pytest.raises(DatasetError, match='does not match'):
        collect_backend(dataset, replay, exp_path, 'laya_current', tmp_path/'wrong-export', allow_overlap=True)
    assert FakeBackend.calls == []
    assert not (tmp_path/'wrong-export').exists()
