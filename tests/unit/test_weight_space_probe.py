import json

import pytest
import torch

from experiments.laya_weight_space.budget import Budget
from experiments.laya_weight_space.probe import observe
from lgh.train.data import DatasetError
from tests.unit.test_weight_space_evaluate import frozen_protocol, samples


def ledger(tmp_path):
    return Budget.create(tmp_path / 'budget.json', protocol_sha256='a' * 64,
                         parent_sha256='b' * 64, arm='W', purpose='tool_smoke')


def test_budget_counts_failures_repeats_and_survives_reload(tmp_path):
    budget = ledger(tmp_path)
    with pytest.raises(RuntimeError):
        with budget.evaluation(['case-1'], 'probe') as call:
            call.forward(7, 'cpu')
            raise RuntimeError('failure')
    reloaded = Budget(budget.path)
    with reloaded.evaluation(['case-1'], 'prediction') as call:
        call.forward(7, 'cpu')
    state = reloaded.snapshot()
    assert state['calls'][0]['status'] == 'failed'
    assert state['calls'][1]['status'] == 'complete'
    assert sum(len(c['case_ids']) for c in state['calls']) == 2
    assert sum(len(c['forwards']) for c in state['calls']) == 2


def test_budget_rejects_limits_before_work_and_never_resets(tmp_path):
    budget = ledger(tmp_path)
    for _ in range(20):
        with budget.evaluation([f'c{i}' for i in range(64)], 'probe'):
            pass
    with pytest.raises(DatasetError, match='budget'):
        with budget.evaluation(['c'], 'probe'):
            pytest.fail('work ran past budget')
    with pytest.raises(FileExistsError):
        ledger(tmp_path)
    assert len(budget.snapshot()['calls']) == 20


@pytest.mark.parametrize('ids', [[], ['c'] * 2, [str(i) for i in range(65)]])
def test_budget_rejects_invalid_batch(tmp_path, ids):
    budget = ledger(tmp_path)
    with pytest.raises(DatasetError):
        with budget.evaluation(ids, 'probe'):
            pytest.fail('invalid batch accepted')
    assert budget.snapshot()['calls'] == []


def test_patch_proposals_and_tampered_budget(tmp_path):
    budget = ledger(tmp_path)
    for i in range(10):
        budget.proposal(str(i))
    with pytest.raises(DatasetError, match='budget'):
        budget.proposal('eleventh')
    raw = json.loads(budget.path.read_text())
    raw['calls'] = ['tampered']
    budget.path.write_text(json.dumps(raw))
    with pytest.raises(DatasetError, match='hash'):
        budget.snapshot()


def test_observation_preserves_output_parameters_and_cleans_hooks_on_failure(tmp_path):
    model = torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.ReLU())
    model.eval()
    x = torch.ones(7, 2)
    expected = model(x).clone()
    weights = {k: v.clone() for k, v in model.state_dict().items()}
    budget = ledger(tmp_path)
    with budget.evaluation(['case'], 'probe') as call:
        with observe(model, ['0'], call) as captured:
            assert torch.equal(model(x), expected)
    assert captured['0'][0]['shape'] == [7, 2]
    assert 'values' not in captured['0'][0]
    with pytest.raises(RuntimeError):
        with budget.evaluation(['case'], 'probe') as call:
            with observe(model, ['0'], call):
                model(x)
                raise RuntimeError('downstream failure')
    assert all(not m._forward_hooks and not m._forward_pre_hooks for m in model.modules())
    assert all(torch.equal(v, weights[k]) for k, v in model.state_dict().items())
    assert torch.equal(model(x), expected)


def test_observation_rejects_unknown_module_and_training_mode(tmp_path):
    model = torch.nn.Sequential(torch.nn.Linear(2, 2)).eval()
    budget = ledger(tmp_path)
    with budget.evaluation(['case'], 'probe') as call:
        with pytest.raises(DatasetError, match='module'):
            with observe(model, ['missing'], call):
                pass
        model.train()
        with pytest.raises(DatasetError, match='eval'):
            with observe(model, ['0'], call):
                pass
    assert not model[0]._forward_hooks


def test_probe_reports_seven_answers_errors_and_never_raw_state(tmp_path, frozen_protocol):
    from experiments.laya_weight_space.probe import run_probe
    from experiments.laya_weight_space.protocol import read_protocol, validate_inputs
    from tests.unit.test_backend_contract import answers, write_inputs
    p = read_protocol(frozen_protocol)
    rows, sides = samples(frozen_protocol)
    paths = write_inputs(tmp_path, rows, sides)
    rows, cases = validate_inputs(*paths, p)

    class Agent:
        model = torch.nn.Sequential(torch.nn.Linear(2, 2)).eval()
        device = torch.device('cpu')

        def predict(self, state, questions):
            self.model(torch.ones(7, 2))
            return {'answers': answers({'questions': questions}, handling='allow', risk=0.1)}

    budget = Budget.create(tmp_path / 'run.json', protocol_sha256=p['sha256'],
                           parent_sha256='b' * 64, arm='W', purpose='tool_smoke')
    result = run_probe(Agent(), rows, cases, p, budget, tensor_names=['0.weight'], module_names=['0'])
    assert len(result['cases']) == 4
    assert len(result['cases'][0]['answers']) == 7
    assert 'false_allow' in result['cases'][0]['errors']
    assert result['cases'][0]['question_errors']['handling'] == {'expected': 'verify', 'predicted': 'allow'}
    assert all('state' not in r and 'envelope' not in r for r in result['cases'])
    assert len(budget.snapshot()['calls'][0]['forwards']) == 4


def test_retry_is_rejected_before_second_forward(tmp_path):
    model = torch.nn.Sequential(torch.nn.Linear(2, 2)).eval()
    budget = ledger(tmp_path)
    with pytest.raises(DatasetError, match='repeated forward'):
        with budget.evaluation(['case'], 'probe') as call:
            with observe(model, ['0'], call):
                model(torch.ones(7, 2))
                model(torch.ones(7, 2))
    assert len(budget.snapshot()['calls'][0]['forwards']) == 1
    assert all(not m._forward_hooks and not m._forward_pre_hooks for m in model.modules())


def test_budget_ticket_cannot_run_after_closed_reservation(tmp_path):
    budget = ledger(tmp_path)
    with budget.evaluation(['case'], 'probe') as call:
        call.forward(7, 'cpu')
    with pytest.raises(DatasetError, match='reservation'):
        call.forward(7, 'cpu')
