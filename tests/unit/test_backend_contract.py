import copy
import json

import pytest

from lgh.eval.backend_contract import (
    Experiment, probability, read_inputs, rule_config_hash, validate_answers,
)
from lgh.laya.client import state_payload
from lgh.laya.questions import load_questions
from lgh.rules.engine import evaluate_rules
from lgh.state.builder import build_laya_state
from lgh.train.data import DatasetError
from tests.helpers import make_envelope


def experiment():
    from lgh.config.models import GuardrailConfig
    cfg = GuardrailConfig()
    cfg.laya.model = 'local-current'
    return Experiment.model_validate({
        'version': 1, 'config': cfg.model_dump(mode='json'),
        'hardware': {'gpu': 'NVIDIA RTX 3090', 'vram_gb': 24},
        'backends': {
            name: {'kind': kind, 'url': f'http://127.0.0.1:{8766 + i}',
                   'model': model, 'revision': 'a' * 40, 'code_revision': 'b' * 40,
                   'device': 'cuda', 'dtype': 'bfloat16', 'provenance': 'released'}
            for i, (name, kind, model) in enumerate([
                ('laya_current', 'laya', 'local-current'),
                ('kev', 'kev', 'jaredpalmer/kev-4b@v1.0'),
                ('laya_released', 'laya', 'convaiinnovations/laya-typed-decisions')])},
    })


def case(exp=None, trace_id='case-1', command='echo hello', requires=False):
    exp = exp or experiment()
    env = make_envelope(command=command)
    row = {'trace_id': trace_id, 'timestamp': env.event.timestamp,
           'state': state_payload(build_laya_state(env)), 'questions': load_questions(),
           'source': 'human', 'labels': {
               'task_alignment': 'aligned', 'reversibility': 'trivial', 'handling': 'allow',
               'destructive_risk': 0.2, 'sensitive_resource': 0, 'external_impact': 0,
               'verification_needed': 0}}
    side = {'trace_id': trace_id, 'envelope': env.model_dump(mode='json', by_alias=True),
            'rules': evaluate_rules(env, exp.config).model_dump(mode='json'),
            'rule_config_sha256': rule_config_hash(exp.config), 'session': {'counters': {}},
            'reference': {'source': 'human', 'requires_intervention': requires,
                          'acceptable': ['REPLAN'] if requires else ['ALLOW'],
                          'forbidden': ['ALLOW'] if requires else []}}
    return row, side


def answers(row, handling='allow', risk=0.1):
    result = {}
    for key, q in row['questions'].items():
        if q['type'] == 'noul':
            result[key] = {'type': 'noul', 'noul': risk}
        else:
            choice = handling if key == 'handling' else next(iter(q['criteria']))
            result[key] = {'type': 'choice', 'choice': choice, 'confidence': 0.123,
                           'probabilities': {k: 0.97 if k == choice else 0.01 for k in q['criteria']}}
    return result


def write_inputs(tmp_path, rows, sides):
    dataset, replay = tmp_path/'data.jsonl', tmp_path/'replay.jsonl'
    dataset.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    replay.write_text(''.join(json.dumps(r)+'\n' for r in sides))
    return dataset, replay


def test_exact_context_join_preserves_soft_labels_and_blind_mode(tmp_path):
    exp = experiment()
    row, side = case(exp)
    paths = write_inputs(tmp_path, [row], [side])
    rows, replay = read_inputs(*paths, exp)
    assert rows[0]['labels']['destructive_risk'] == 0.2
    assert replay[0].reference.requires_intervention is False
    rows, replay = read_inputs(*paths, exp, unlabeled=True)
    assert 'labels' not in rows[0]
    assert replay[0].reference is None


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'state', 'config', 'reference'])
def test_bad_replay_context_is_rejected_before_inference(tmp_path, mutation):
    exp = experiment()
    row, side = case(exp)
    sides = [side]
    if mutation == 'missing': sides = []
    if mutation == 'duplicate': sides.append(copy.deepcopy(side))
    if mutation == 'state': side['envelope']['action']['command'] = 'echo changed'
    if mutation == 'config': side['rule_config_sha256'] = '0'*64
    if mutation == 'reference': side['reference']['source'] = 'laya'
    with pytest.raises((DatasetError, ValueError)):
        read_inputs(*write_inputs(tmp_path, [row], sides), exp)


@pytest.mark.parametrize('value', [True, '0.5', float('nan'), float('inf'), -0.1, 1.1])
def test_invalid_probabilities_are_not_clipped(value):
    with pytest.raises(DatasetError): probability(value)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'type', 'option', 'sum', 'choice', 'nan'])
def test_invalid_model_answers_are_rejected(mutation):
    row, _ = case()
    result = answers(row)
    if mutation == 'missing': result.pop('handling')
    if mutation == 'extra': result['other'] = result['handling']
    if mutation == 'type': result['handling']['type'] = 'score'
    if mutation == 'option': result['handling']['probabilities']['bad'] = 0
    if mutation == 'sum': result['handling']['probabilities']['allow'] = 0.1
    if mutation == 'choice': result['handling']['choice'] = 'escalate'
    if mutation == 'nan': result['external_impact']['noul'] = float('nan')
    with pytest.raises(DatasetError): validate_answers(result, row['questions'])


def test_vendor_confidence_does_not_override_probability_and_rounding_is_allowed():
    row, _ = case()
    result = answers(row)
    result['handling']['probabilities']['allow'] = 0.9699
    assert validate_answers(result, row['questions']) == result


def test_unknown_config_fields_and_candidate_fallback_are_rejected():
    data = experiment().model_dump(mode='json')
    data['config']['laya']['threshholds'] = {}
    with pytest.raises(ValueError): Experiment.model_validate(data)
    data = experiment().model_dump(mode='json')
    data['backends']['kev']['model'] = 'jaredpalmer/kev-0.8b'
    with pytest.raises(ValueError): Experiment.model_validate(data)


def test_every_row_must_preserve_option_order_not_only_first(tmp_path):
    exp = experiment()
    first, side1 = case(exp, trace_id='one')
    second, side2 = case(exp, trace_id='two')
    q = second['questions']['handling']
    q['criteria'] = dict(reversed(list(q['criteria'].items())))
    with pytest.raises(DatasetError, match='order'):
        read_inputs(*write_inputs(tmp_path, [first, second], [side1, side2]), exp)


def test_full_envelope_cannot_smuggle_credentials_outside_compact_state(tmp_path):
    exp = experiment()
    row, side = case(exp)
    side['envelope']['action']['arguments'] = {'authorization': 'Bearer private-test-value'}
    with pytest.raises(DatasetError, match='redact'):
        read_inputs(*write_inputs(tmp_path, [row], [side]), exp)
