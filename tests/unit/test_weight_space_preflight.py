import json
from pathlib import Path

import pytest

from experiments.laya_weight_space import preflight
from lgh.eval.compare import file_hash


def checkpoint(path: Path, training: dict | None = None) -> Path:
    path.mkdir()
    for name in preflight.REQUIRED_FILES:
        target = path / name
        target.parent.mkdir(exist_ok=True)
        target.write_text('{}' if target.suffix == '.json' else 'fixture-weights')
    (path / 'rl_agent_config.json').write_text(json.dumps({
        'lgh_training': training or {}, 'temperature_by_options': {'noul:2': 1.05},
    }))
    return path


def test_checkpoint_identity_covers_tokenizer_encoder_and_weights(tmp_path):
    base = checkpoint(tmp_path / 'base')
    first = preflight.checkpoint_snapshot(base)
    assert len(first['files']) == len(preflight.REQUIRED_FILES)
    (base / 'tokenizer/tokenizer.json').write_text('{"changed": true}')
    second = preflight.checkpoint_snapshot(base)
    assert first['identity_sha256'] != second['identity_sha256']
    assert first['files']['model.safetensors'] == second['files']['model.safetensors']
    (base / 'encoder/config.json').unlink()
    with pytest.raises(ValueError, match='missing checkpoint files'):
        preflight.checkpoint_snapshot(base)


def test_history_checks_content_instead_of_trusting_declared_hash(tmp_path):
    data = tmp_path / 'train.jsonl'
    data.write_text('{"source":"human"}\n')
    metadata = {'dataset_sha256': file_hash(data), 'base': 'upstream/model'}
    assert preflight.training_history(metadata, data)['datasets']['train']['status'] == 'verified'
    data.write_text('changed')
    assert preflight.training_history(metadata, data)['datasets']['train']['status'] == 'hash_mismatch'
    data.unlink()
    assert preflight.training_history(metadata, data)['datasets']['train']['status'] == 'missing'
    assert preflight.training_history(metadata, None)['datasets']['train']['status'] == 'missing'


def test_history_records_separate_partitions_and_unknown_upstream(tmp_path):
    data = tmp_path / 'validation.jsonl'
    data.write_text('{}\n')
    history = preflight.training_history({'datasets': {
        'validation': {'path': str(data), 'sha256': file_hash(data)},
    }}, None)
    assert history['datasets']['validation']['status'] == 'verified'
    assert history['upstream_pretraining'] == 'unknown'


def test_session_evidence_uses_latest_turn_not_defaults_and_omits_content(tmp_path):
    path = tmp_path / 'session.jsonl'
    rows = [
        {'type': 'session_meta', 'payload': {'id': 'ours'}},
        {'type': 'turn_context', 'payload': {'model': 'gpt-6-astra', 'turn_id': 'old'}},
        {'type': 'response_item', 'payload': {'content': 'PRIVATE CONTENT'}},
        {'type': 'turn_context', 'payload': {'model': 'other-model', 'turn_id': 'new',
                                         'secret': 'PRIVATE CONTENT'}},
    ]
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows) + '{')
    evidence = preflight.session_evidence(path, 'ours')
    assert evidence['model'] == 'other-model'
    assert evidence['turn_id'] == 'new'
    assert evidence['status'] == 'model_mismatch'
    assert 'PRIVATE CONTENT' not in json.dumps(evidence)
    assert preflight.session_evidence(path, 'someone-else')['status'] == 'thread_mismatch'
    assert preflight.session_evidence(path, None)['status'] == 'thread_unverified'


@pytest.fixture
def environment(tmp_path, monkeypatch):
    data = tmp_path / 'train.jsonl'
    data.write_text('{}\n')
    base = checkpoint(tmp_path / 'base', {'dataset_sha256': file_hash(data)})
    config = {'configured_model': str(base), 'effective_sha256': 'fixed', 'files': {}}
    monkeypatch.setattr(preflight, 'configuration_snapshot', lambda cwd: dict(config))
    monkeypatch.setattr(preflight, 'current_session', lambda: {
        'status': 'verified', 'model': 'gpt-6-astra', 'turn_id': 'test',
    })
    monkeypatch.setattr(preflight, 'tensor_probe', lambda: {
        'cpu': {'status': 'passed'}, 'cuda': {'status': 'passed'},
    })
    monkeypatch.setattr(preflight, 'gpu_snapshot', lambda: {'observed': [{'name': 'test GPU'}]})
    return base, data, config


def test_preflight_preserves_inputs_and_locks_repeatable_identity(tmp_path, environment):
    base, data, _ = environment
    before = preflight.checkpoint_snapshot(base)
    one = preflight.run_preflight(tmp_path / 'one', cwd=tmp_path, base_training=data)
    two = preflight.run_preflight(tmp_path / 'two', cwd=tmp_path, base_training=data)
    assert one['status'] == 'complete'
    assert one['base'] == two['base'] == before == preflight.checkpoint_snapshot(base)
    assert one['integrity']['unchanged'] is True
    assert one['budget']['new_api_requests'] == 0
    assert one['experiment_ready'] is False
    saved = json.loads((tmp_path / 'one/manifest.json').read_text())
    assert saved == one
    with pytest.raises(ValueError, match='already exists'):
        preflight.run_preflight(tmp_path / 'one', cwd=tmp_path, base_training=data)


def test_missing_gpu_or_astra_remains_pending(tmp_path, environment, monkeypatch):
    _, data, _ = environment
    monkeypatch.setattr(preflight, 'current_session', lambda: {'status': 'not_found'})
    monkeypatch.setattr(preflight, 'gpu_snapshot', lambda: {'observed': None})
    monkeypatch.setattr(preflight, 'tensor_probe', lambda: {
        'cpu': {'status': 'passed'}, 'cuda': {'status': 'unavailable'},
    })
    result = preflight.run_preflight(tmp_path / 'out', cwd=tmp_path, base_training=data)
    assert result['status'] == 'pending'
    assert {'astra_session', 'gpu_telemetry', 'cuda_probe'} <= set(result['pending'])


def test_missing_runtime_package_is_not_a_complete_preflight(tmp_path, environment, monkeypatch):
    _, data, _ = environment
    monkeypatch.setattr(preflight, 'package_versions', lambda: {'laya': None})
    result = preflight.run_preflight(tmp_path / 'out', cwd=tmp_path, base_training=data)
    assert result['status'] == 'pending'
    assert 'runtime_packages' in result['pending']


@pytest.mark.parametrize('mutation', ['weights', 'config', 'dataset'])
def test_changes_during_inventory_are_not_reported_as_locked(tmp_path, environment, monkeypatch, mutation):
    base, data, config = environment

    def mutate():
        if mutation == 'config':
            config['effective_sha256'] = 'changed'
        else:
            (data if mutation == 'dataset' else base / 'model.safetensors').write_text('changed')
        return {'cpu': {'status': 'passed'}, 'cuda': {'status': 'passed'}}

    monkeypatch.setattr(preflight, 'tensor_probe', mutate)
    result = preflight.run_preflight(tmp_path / 'out', cwd=tmp_path, base_training=data)
    assert result['status'] == 'pending'
    assert result['integrity']['unchanged'] is False


def test_output_must_not_be_inside_checkpoint(tmp_path, environment):
    base, data, _ = environment
    with pytest.raises(ValueError, match='inside checkpoint'):
        preflight.run_preflight(base / 'out', cwd=tmp_path, base_training=data)
    assert not (base / 'out').exists()
