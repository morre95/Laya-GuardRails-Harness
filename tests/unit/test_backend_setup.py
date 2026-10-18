import json

import pytest

from lgh.eval.backend_setup import snapshot_experiment
from lgh.config.models import GuardrailConfig
from lgh.train.data import DatasetError


def test_snapshot_records_current_checkpoint_without_loading_or_reconfiguring(tmp_path, monkeypatch):
    from lgh.eval import backend_setup
    cfg = GuardrailConfig()
    model = tmp_path/'checkpoint'
    model.mkdir()
    (model/'model.safetensors').write_bytes(b'test-weights')
    (model/'rl_agent_config.json').write_text(json.dumps({'lgh_training': {'dataset_sha256': 'c'*64}}))
    cfg.laya.model = str(model)
    monkeypatch.setattr(backend_setup, 'load_config', lambda **kw: cfg)
    monkeypatch.setattr(backend_setup, 'gpu_snapshot', lambda: {'observed': [{'name':'RTX 3090'}]})
    before = cfg.model_dump(mode='json')
    output = tmp_path/'setup'
    snapshot_experiment(output, cwd=tmp_path)
    exp = json.loads((output/'experiment.json').read_text())
    assert exp['backends']['kev']['model'] == 'jaredpalmer/kev-4b@v1.0'
    assert exp['backends']['kev']['revision'] is None
    assert exp['backends']['laya_current']['provenance'] == 'local_finetuned'
    assert len(exp['backends']['laya_current']['revision']) == 64
    assert exp['config'] == before == cfg.model_dump(mode='json')
    assert exp['backends']['laya_current']['device'] == 'cpu'
    assert 'rule_config_sha256' in json.loads((output/'setup.json').read_text())
    with pytest.raises(DatasetError): snapshot_experiment(output, cwd=tmp_path)
