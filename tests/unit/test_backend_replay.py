import copy

import pytest

from lgh.eval.backend_contract import ReplayCase
from lgh.eval.backend_replay import replay_assessment
from tests.unit.test_backend_contract import answers, case, experiment


def test_frozen_replay_changes_only_model_dependent_decisions(monkeypatch):
    from lgh import pipeline
    def forbidden(*args, **kwargs): raise AssertionError('live context or execution used')
    monkeypatch.setattr(pipeline, 'apply_environment', forbidden)
    monkeypatch.setattr(pipeline, 'evaluate_rules', forbidden)
    monkeypatch.setattr(pipeline, 'build_laya_state', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    exp = experiment()
    row, side = case(exp)
    snapshot = ReplayCase.model_validate(side)
    before = exp.model_dump(mode='json')
    allow = replay_assessment(row, snapshot, exp, 'laya_current', answers(row))
    risky = replay_assessment(row, snapshot, exp, 'kev', answers(row, risk=0.99))
    assert allow['policy_decision'] == 'ALLOW'
    assert risky['policy_decision'] == 'FRONTIER_REVIEW'
    assert risky['final_decision'] == 'HUMAN_APPROVAL'
    assert risky['model_dependent'] is True
    assert risky['approval_granted'] is False
    assert exp.model_dump(mode='json') == before


def test_hard_rule_overrides_both_models_and_bypasses_normalization():
    exp = experiment()
    row, side = case(exp, command='rm -rf /', requires=True)
    snapshot = ReplayCase.model_validate(side)
    result = replay_assessment(row, snapshot, exp, 'kev', answers(row))
    assert result['model_dependent'] is False
    assert result['assessment'] is None
    assert result['final_decision'] == 'BLOCK'


def test_each_case_repeat_starts_from_identical_antiloop_snapshot():
    from lgh.session.antiloop import action_key
    exp = experiment()
    row, side = case(exp)
    key = action_key('echo hello', None, 'shell', 'execute')
    side['session']['counters'][key] = {'verification': 2, 'replan': 0, 'frontier': 0}
    snapshot = ReplayCase.model_validate(side)
    original = copy.deepcopy(side['session'])
    results = [replay_assessment(row, snapshot, exp, 'laya_current', answers(row, handling='verify')) for _ in range(3)]
    assert {r['final_decision'] for r in results} == {'HUMAN_APPROVAL'}
    assert side['session'] == original
    assert snapshot.session == original


@pytest.mark.parametrize('handling,decision', [('allow','ALLOW'), ('verify','ALLOW_WITH_VERIFICATION'),
                                             ('replan','REPLAN'), ('escalate','HUMAN_APPROVAL')])
def test_offline_routes_and_fixed_input_pipeline_parity(tmp_path, handling, decision):
    from lgh.config.models import GuardrailConfig
    from lgh.frontier.stub import StubReviewer
    from lgh.laya.client import FakeLayaClient
    from lgh.laya.normalize import normalize_assessment
    from lgh.pipeline import Pipeline
    from lgh.session.store import SessionStore
    from lgh.trace.writer import TraceWriter
    exp = experiment()
    row, side = case(exp)
    snapshot = ReplayCase.model_validate(side)
    prediction = answers(row, handling=handling)
    normalized = normalize_assessment({'answers': prediction}, model='test', latency_ms=0)
    cfg = exp.config.model_copy(deep=True)
    cfg.mode = 'enforce'
    live = Pipeline(cfg, laya=FakeLayaClient(normalized), reviewer=StubReviewer(unavailable=True),
                    sessions=SessionStore(tmp_path/'sessions'), traces=TraceWriter(tmp_path/'traces'))
    # Resolved development environment outranks live detection for this fixed case.
    env = snapshot.envelope.model_copy(update={'environment': snapshot.envelope.environment.model_copy(update={'confidence': 1})})
    expected = live.evaluate(env)
    result = replay_assessment(row, snapshot, exp, 'laya_current', prediction)
    assert result['final_decision'] == decision == expected.decision
    assert result['policy_decision'] == expected.policy_decision


def test_current_laya_temperatures_are_not_applied_to_kev():
    raw = experiment().model_dump(mode='json')
    raw['config']['laya']['temperatures'] = {'noul': 3}
    raw['backends']['laya_current']['temperatures'] = {'noul': 3}
    from lgh.eval.backend_contract import Experiment
    exp = Experiment.model_validate(raw)
    row, side = case(exp)
    snapshot = ReplayCase.model_validate(side)
    current = replay_assessment(row, snapshot, exp, 'laya_current', answers(row, risk=0.9))
    kev = replay_assessment(row, snapshot, exp, 'kev', answers(row, risk=0.9))
    assert current['final_decision'] == 'ALLOW'
    assert kev['final_decision'] == 'HUMAN_APPROVAL'


@pytest.mark.parametrize('message', ['internal reviewer bug', ''])
def test_unexpected_reviewer_failure_is_not_counted_as_normal_escalation(monkeypatch, message):
    def broken(*args): raise RuntimeError(message)
    monkeypatch.setattr('lgh.frontier.stub.StubReviewer.review', broken)
    exp = experiment()
    row, side = case(exp)
    from lgh.train.data import DatasetError
    with pytest.raises(DatasetError, match='offline replay failed'):
        replay_assessment(row, ReplayCase.model_validate(side), exp, 'kev', answers(row, risk=0.99))
