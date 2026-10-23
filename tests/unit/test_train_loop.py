"""Small real-tensor regressions, requiring no checkpoint or GPU."""
import random
from types import SimpleNamespace

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('laya')
from lgh.train.loop import TrainSettings, _train_epoch


def test_partial_accumulation_window_has_full_weight(monkeypatch):
    import lgh.train.loop as loop

    model = torch.nn.Linear(1, 1, bias=False)
    model.weight.data.zero_()
    agent = SimpleNamespace(model=model)
    monkeypatch.setattr(loop, '_forward', lambda agent, item: (agent.model.weight.sum(), None))
    monkeypatch.setattr(loop, '_log_loss', lambda prediction, target: prediction)
    optimizer = torch.optim.SGD(model.parameters(), lr=1.0)
    _train_epoch(agent, [[], [], []], optimizer, TrainSettings(grad_accumulation=2), random.Random(0))
    # Two updates, each from a mean gradient of 1, including the final singleton.
    assert model.weight.item() == pytest.approx(-2.0)


@pytest.mark.parametrize('settings', [
    {'epochs': 0}, {'grad_accumulation': 0}, {'patience': -1},
    {'lr_encoder': float('nan')}, {'lr_head': -1},
])
def test_invalid_training_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        TrainSettings(**settings)
