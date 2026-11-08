import json
from pathlib import Path

import pytest

from experiments.laya_weight_space import run_training as ws
from experiments.laya_weight_space.protocol import read_protocol, seal, write_json
from lgh.eval.compare import file_hash
from lgh.train.data import DatasetError
from tests.unit.test_weight_space_evaluate import frozen_protocol, samples
from tests.unit.test_backend_contract import answers


@pytest.fixture
def inputs(tmp_path, frozen_protocol):
    from tests.unit.test_backend_contract import write_inputs
    p = read_protocol(frozen_protocol)
    root = tmp_path / 'partitions'
    root.mkdir()
    files = {}
    for i, name in enumerate(ws.PARTITIONS):
        directory = root / name
        directory.mkdir()
        rows, sides = samples(frozen_protocol, n=8)
        data, replay = write_inputs(directory, rows[i * 2:i * 2 + 2], sides[i * 2:i * 2 + 2])
        for source, target in [(data, 'dataset.jsonl'), (replay, 'replay.jsonl')]:
            if source != directory / target:
                source.rename(directory / target)
            files[f'{name}/{target}'] = file_hash(directory / target)
    write_json(root / 'manifest.json', seal(dict(version=1, kind='weight_space_partitions',
        development_ready=True, status='open_development_only', protocol_sha256=p['sha256'],
        files=files, source_hashes={})))
    return frozen_protocol, root


def test_inputs_reject_changed_partition_and_base(inputs):
    protocol, root = inputs
    p, manifest, splits = ws.read_training_inputs(protocol, root)
    assert set(splits) == set(ws.PARTITIONS)
    base = Path(p['base']['path']) / 'model.safetensors'
    original = base.read_bytes()
    base.write_bytes(b'changed')
    with pytest.raises(DatasetError, match='base'):
        ws.read_training_inputs(protocol, root)
    base.write_bytes(original)
    with (root / 'calibration/dataset.jsonl').open('a') as stream:
        stream.write('\n')
    with pytest.raises(DatasetError, match='hash'):
        ws.read_training_inputs(protocol, root)


def test_temperature_copy_changes_only_config_and_never_base(tmp_path, frozen_protocol):
    from experiments.laya_weight_space.preflight import checkpoint_snapshot
    p = read_protocol(frozen_protocol)
    base = Path(p['base']['path'])
    before = checkpoint_snapshot(base)
    output = tmp_path / 'calibrated'
    ws.copy_with_temperatures(base, output, {'noul:2': 2.0})
    after = checkpoint_snapshot(output)
    assert checkpoint_snapshot(base) == before
    assert after['files']['model.safetensors'] == before['files']['model.safetensors']
    assert {k for k in before['files'] if before['files'][k] != after['files'][k]} == {'rl_agent_config.json'}
    assert after['temperatures'] == {'noul:2': 2.0}
    with pytest.raises(FileExistsError):
        ws.copy_with_temperatures(base, output, {})


def test_comparison_retains_individual_regressions(frozen_protocol):
    from experiments.laya_weight_space.protocol import validate_inputs
    from tests.unit.test_backend_contract import write_inputs
    p = read_protocol(frozen_protocol)
    rows, sides = samples(frozen_protocol)
    paths = write_inputs(frozen_protocol.parent, rows, sides)
    rows, cases = validate_inputs(*paths, p)
    choices = {'B': ['allow', 'allow', 'verify', 'allow'],
               'D': ['verify', 'verify', 'allow', 'allow'],
               'B_operational': ['allow', 'allow', 'verify', 'allow'],
               'B_unit_temperature': ['allow'] * 4,
               'D_unit_temperature': ['verify'] * 4}
    predictions = {arm: [answers(r, handling=c, risk=0.1) for r, c in zip(rows, cs)]
                   for arm, cs in choices.items()}
    report, routed = ws.compare_development(p, rows, cases, predictions)
    result = report['pairs']['B_to_D']['all']
    assert result['before']['false_allows'] == 2
    assert result['after']['false_allows'] == 1
    assert result['new_false_allows'] == ['case-2']
    assert result['observed_gate']['passes'] is False
    assert set(routed) == set(choices)
    assert report['selection'] == 'not_evaluated_for_promotion'
    predictions['D'][0].pop('handling')
    with pytest.raises(DatasetError):
        ws.compare_development(p, rows, cases, predictions)


def test_failed_attempt_is_journaled_and_cannot_be_overwritten(tmp_path, inputs, monkeypatch):
    from lgh.train.loop import TrainSettings
    protocol, root = inputs
    output = tmp_path / 'attempt'
    monkeypatch.setattr(ws, 'current_session', lambda: {'status': 'verified', 'model': 'gpt-6-astra'})

    def fail(*args, **kwargs):
        raise RuntimeError('fixture GPU failure')

    monkeypatch.setattr(ws, 'execute_models', fail)
    with pytest.raises(RuntimeError, match='GPU failure'):
        ws.run(protocol, root, output, TrainSettings(), 'cuda')
    plan = json.loads((output / 'plan.json').read_text())
    assert plan['settings']['seed'] == 0 and plan['attempt_budget'] == 1
    failure = json.loads((output / 'failure.json').read_text())
    assert failure['status'] == 'failed' and failure['error'] == 'fixture GPU failure'
    assert 'failed' in (output / 'journal.jsonl').read_text()
    with pytest.raises(DatasetError, match='exists'):
        ws.run(protocol, root, output, TrainSettings(), 'cuda')


def test_refuses_output_inside_frozen_inputs(tmp_path, inputs):
    from lgh.train.loop import TrainSettings
    protocol, root = inputs
    with pytest.raises(DatasetError, match='inside'):
        ws.run(protocol, root, root / 'new-attempt', TrainSettings(), 'cuda')
    assert not (root / 'new-attempt').exists()


def test_manifest_binds_completed_artifacts_and_separate_calibration(inputs, tmp_path, monkeypatch):
    from lgh.train.loop import TrainSettings
    from experiments.laya_weight_space.protocol import read_sealed
    protocol, directory = inputs
    monkeypatch.setattr(ws, 'current_session', lambda: {'status': 'verified'})

    def fixture_models(p, directory, output, splits, settings, device, log):
        # Exercise publication/integrity only; no model-quality claim from this fixture.
        assert len(splits['calibration'][0]) == 2
        write_json(output / 'predictions.json', {'fixture': True})
        return {'D_for_DW': {'fixture': True}}

    monkeypatch.setattr(ws, 'execute_models', fixture_models)
    out = tmp_path / 'completed'
    report = ws.run(protocol, directory, out, TrainSettings(), 'cuda')
    manifest = read_sealed(out / 'manifest.json')
    assert report['status'] == 'complete_open_development'
    assert report['cost']['new_api_requests'] == 0
    assert all(file_hash(out / name) == sha for name, sha in manifest['files'].items())
    assert 'report.json' in manifest['files'] and 'predictions.json' in manifest['files']


def test_input_drift_during_attempt_prevents_success(inputs, tmp_path, monkeypatch):
    from lgh.train.loop import TrainSettings
    protocol, directory = inputs
    monkeypatch.setattr(ws, 'current_session', lambda: {'status': 'verified'})

    def change(*args):
        with (directory / 'development/dataset.jsonl').open('a') as stream:
            stream.write('\n')
        return {'D_for_DW': {}}

    monkeypatch.setattr(ws, 'execute_models', change)
    out = tmp_path / 'drift'
    with pytest.raises(DatasetError, match='hash'):
        ws.run(protocol, directory, out, TrainSettings(), 'cuda')
    assert (out / 'failure.json').exists()
    assert not (out / 'report.json').exists()
    assert not (out / 'manifest.json').exists()
