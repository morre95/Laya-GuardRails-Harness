import json

import pytest

from lgh.eval.model_comparison import collect_model_pass, combine_model_passes
from lgh.train.data import DatasetError
from tests.unit.test_backend_contract import answers, case, experiment


class ModelBackend:
    calls = []
    fail = False

    def __init__(self, spec, **kwargs):
        self.spec = spec

    def identity(self):
        return {'observed': {'model': self.spec.model}, 'declared': self.spec.model_dump(mode='json')}

    def predict(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            raise DatasetError('endpoint failed')
        # Repeats intentionally disagree with the first measured response.
        handling = 'allow' if len(self.calls) <= 2 else 'verify'
        return {'answers': answers({'questions': questions}, handling=handling),
                'client_latency_ms': 10, 'server_latency_ms': 8, 'usage': {}, 'prefix_cache_hit': None}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr('lgh.eval.model_comparison.HttpBackend', ModelBackend)
    monkeypatch.setattr('lgh.eval.model_comparison.gpu_snapshot', lambda: {})
    ModelBackend.calls = []
    ModelBackend.fail = False
    row, _ = case()
    dataset = tmp_path / 'dataset.jsonl'
    dataset.write_text(json.dumps(row) + '\n')
    exp = tmp_path / 'experiment.json'
    exp.write_text(experiment().model_dump_json())
    return dataset, exp


def passes(tmp_path, inputs):
    result = []
    for backend in ('laya_current', 'laya_released', 'kev'):
        ModelBackend.calls = []
        output = tmp_path / backend
        collect_model_pass(*inputs, backend, output, log=lambda _: None)
        result.append(output)
    return result


def test_only_model_inputs_are_sent_and_repeats_do_not_inflate_quality(tmp_path, inputs):
    runs = passes(tmp_path, inputs)
    assert len(ModelBackend.calls) == 4
    row = json.loads(inputs[0].read_text())
    assert ModelBackend.calls[0][0] != row['state']
    assert ModelBackend.calls[1] == (row['state'], row['questions'])
    report = combine_model_passes(runs, tmp_path / 'report')
    assert report['comparison_kind'] == 'model_only'
    assert 'harness' not in report
    assert report['selection']['status'] == 'inconclusive'
    assert report['models']['kev']['handling']['intervention']['safe'] == 1
    assert report['models']['kev']['handling']['intervention']['unnecessary'] == 0
    assert report['latency']['kev']['http']['first_pass']['n'] == 1
    assert report['latency']['kev']['http']['repeated_pass']['n'] == 2
    assert not (runs[0] / 'decisions.jsonl').exists()
    with pytest.raises(DatasetError):
        collect_model_pass(*inputs, 'kev', runs[2])


def test_failed_pass_cannot_produce_a_report(tmp_path, inputs):
    ModelBackend.fail = True
    out = tmp_path / 'failed'
    with pytest.raises(DatasetError, match='endpoint failed'):
        collect_model_pass(*inputs, 'kev', out, log=lambda _: None)
    assert json.loads((out / 'manifest.json').read_text())['status'] == 'incomplete'
    with pytest.raises(DatasetError, match='incomplete'):
        combine_model_passes([out], tmp_path / 'report')
    assert not (tmp_path / 'report').exists()


def test_interruption_records_an_incomplete_pass(tmp_path, inputs, monkeypatch):
    def interrupted(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(ModelBackend, 'predict', interrupted)
    out = tmp_path / 'interrupted'
    with pytest.raises(KeyboardInterrupt):
        collect_model_pass(*inputs, 'kev', out)
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['status'] == 'incomplete'
    assert manifest['failure']['type'] == 'KeyboardInterrupt'


@pytest.mark.parametrize('mutation', ['predictions', 'duplicate', 'missing', 'inputs'])
def test_combiner_rejects_changed_or_incompatible_passes(tmp_path, inputs, mutation):
    runs = passes(tmp_path, inputs)
    if mutation == 'predictions':
        (runs[0] / 'predictions.jsonl').write_text('')
    elif mutation == 'duplicate':
        runs[1] = runs[0]
    elif mutation == 'missing':
        runs.pop()
    else:
        data = json.loads(inputs[0].read_text())
        data['state']['goal'] += ' changed'
        inputs[0].write_text(json.dumps(data) + '\n')
        ModelBackend.calls = []
        replacement = tmp_path / 'replacement'
        collect_model_pass(*inputs, 'kev', replacement, log=lambda _: None)
        runs[2] = replacement
    with pytest.raises(DatasetError):
        combine_model_passes(runs, tmp_path / 'report')
    assert not (tmp_path / 'report').exists()


def test_invalid_question_order_fails_before_inference(tmp_path, inputs):
    data = json.loads(inputs[0].read_text())
    data['questions']['handling']['criteria'] = dict(reversed(list(data['questions']['handling']['criteria'].items())))
    inputs[0].write_text(json.dumps(data) + '\n')
    with pytest.raises(DatasetError, match='questions'):
        collect_model_pass(*inputs, 'kev', tmp_path / 'bad')
    assert ModelBackend.calls == []
