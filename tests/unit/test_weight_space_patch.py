import pytest
import torch
from safetensors.torch import load_file, save_file

from experiments.laya_weight_space.patch import apply_patch, restore
from experiments.laya_weight_space.preflight import checkpoint_snapshot
from lgh.train.data import DatasetError
from tests.unit.test_weight_space_preflight import checkpoint


@pytest.fixture
def base(tmp_path):
    path = checkpoint(tmp_path / 'base')
    save_file({'scorer.3.weight': torch.tensor([[1., 2.]]),
               'encoder.weight': torch.tensor([3.]), 'temperature': torch.ones(3)},
              str(path / 'model.safetensors'))
    return path


def patch(base, tmp_path, replacement, **kwargs):
    source = tmp_path / 'replacement.safetensors'
    save_file(replacement, str(source))
    return apply_patch(base, source, tmp_path / 'patch',
        expected_base_sha256=kwargs.pop('expected_base_sha256', checkpoint_snapshot(base)['identity_sha256']),
        allowed_tensors=kwargs.pop('allowed_tensors', ['scorer.3.weight']),
        hypothesis='fixture-only change', **kwargs)


def test_patch_changes_only_declared_tensor_and_restores_exact_bytes(base, tmp_path):
    before = checkpoint_snapshot(base)
    report = patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[1., 5.]])})
    candidate = tmp_path / 'patch/checkpoint'
    changed = load_file(str(candidate / 'model.safetensors'))
    assert torch.equal(changed['scorer.3.weight'], torch.tensor([[1., 5.]]))
    assert torch.equal(changed['encoder.weight'], torch.tensor([3.]))
    assert report['changes']['scorer.3.weight']['changed_parameters'] == 1
    assert report['changes']['scorer.3.weight']['delta_l2'] == 3
    assert checkpoint_snapshot(base) == before
    restored = tmp_path / 'restored'
    restore(base, tmp_path / 'patch', restored)
    assert checkpoint_snapshot(restored)['files'] == before['files']
    with pytest.raises(DatasetError, match='exists'):
        restore(base, tmp_path / 'patch', restored)


def test_zero_patch_preserves_checkpoint_bytes(base, tmp_path):
    before = checkpoint_snapshot(base)
    report = patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[1., 2.]])})
    assert report['changed_parameters'] == 0
    assert checkpoint_snapshot(tmp_path / 'patch/checkpoint')['files'] == before['files']
    with pytest.raises(DatasetError, match='exists'):
        patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[1., 2.]])})


@pytest.mark.parametrize('kind', ['nan', 'inf', 'shape', 'dtype', 'unknown', 'forbidden', 'base', 'encoder'])
def test_invalid_patch_rejected_before_output(base, tmp_path, kind):
    values, kwargs = {'scorer.3.weight': torch.tensor([[1., 2.]])}, {}
    if kind == 'nan': values['scorer.3.weight'][0, 0] = float('nan')
    if kind == 'inf': values['scorer.3.weight'][0, 0] = float('inf')
    if kind == 'shape': values['scorer.3.weight'] = torch.ones(3)
    if kind == 'dtype': values['scorer.3.weight'] = torch.ones(1, 2, dtype=torch.float64)
    if kind == 'unknown': values = {'scorer.unknown': torch.ones(2)}
    if kind == 'forbidden': values = {'temperature': torch.ones(3)}
    if kind == 'base': kwargs['expected_base_sha256'] = '0' * 64
    if kind == 'encoder':
        values = {'encoder.weight': torch.ones(1)}
        kwargs['allowed_tensors'] = ['encoder.weight']
    with pytest.raises(DatasetError):
        patch(base, tmp_path, values, **kwargs)
    assert not (tmp_path / 'patch').exists()


def test_restore_rejects_changed_candidate_or_base(base, tmp_path):
    patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[1., 5.]])})
    (tmp_path / 'patch/checkpoint/config.json').write_text('{"changed":true}')
    with pytest.raises(DatasetError, match='candidate'):
        restore(base, tmp_path / 'patch', tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()


def test_patch_refuses_nested_output_and_symlinks(base, tmp_path):
    source = tmp_path / 'replacement.safetensors'
    save_file({'scorer.3.weight': torch.tensor([[1., 2.]])}, str(source))
    kwargs = dict(expected_base_sha256=checkpoint_snapshot(base)['identity_sha256'],
                  allowed_tensors=['scorer.3.weight'], hypothesis='fixture')
    with pytest.raises(DatasetError, match='inside'):
        apply_patch(base, source, base / 'nested', **kwargs)
    (base / 'link').symlink_to(source)
    with pytest.raises(DatasetError, match='symlink'):
        apply_patch(base, source, tmp_path / 'patch', **kwargs)


def test_patch_preserves_exact_replacement_bits_including_signed_zero(base, tmp_path):
    save_file({'scorer.3.weight': torch.tensor([[0., 2.]])}, str(base / 'model.safetensors'))
    report = patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[-0., 2.]])})
    value = load_file(str(tmp_path / 'patch/checkpoint/model.safetensors'))['scorer.3.weight']
    assert torch.signbit(value[0, 0])
    assert report['changed_parameters'] == 1


def test_patch_accepts_read_only_original_weight_file(base, tmp_path):
    (base / 'model.safetensors').chmod(0o444)
    patch(base, tmp_path, {'scorer.3.weight': torch.tensor([[1., 5.]])})
    assert load_file(str(base / 'model.safetensors'))['scorer.3.weight'][0, 1] == 2
