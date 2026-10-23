from pathlib import Path

import pytest

from lgh.train.data import DatasetError
from tests.unit.test_train import make_row, write_rows


@pytest.mark.parametrize('partition', ['validation', 'calibration'])
def test_training_rejects_partition_overlap_before_loading_model(tmp_path, monkeypatch, partition):
    laya = pytest.importorskip('laya')
    from lgh.train.loop import TrainSettings
    from lgh.train.runner import run_training

    def forbidden(*args, **kwargs):
        pytest.fail('model must not load when data is invalid')

    monkeypatch.setattr(laya, 'load', forbidden)
    paths = {name: tmp_path / f'{name}.jsonl' for name in ('train', 'validation', 'calibration')}
    for index, path in enumerate(paths.values()):
        write_rows(path, [make_row(index)])
    write_rows(paths[partition], [make_row(0)])
    with pytest.raises(DatasetError, match='overlap'):
        run_training(paths['train'], tmp_path / 'out', 'unused', 'cpu', TrainSettings(),
                     validation=paths['validation'], calibration=paths['calibration'])


def test_calibration_requires_explicit_validation(tmp_path):
    pytest.importorskip('laya')
    from lgh.train.loop import TrainSettings
    from lgh.train.runner import run_training

    with pytest.raises(DatasetError, match='requires explicit validation'):
        run_training(Path('unused'), tmp_path / 'out', 'unused', 'cpu', TrainSettings(),
                     calibration=Path('unused'))
