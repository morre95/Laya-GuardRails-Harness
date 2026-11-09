"""Exact tensor replacements in new checkpoints; original files are only read."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from safetensors.torch import load_file, save_file
import torch

from experiments.laya_weight_space.preflight import checkpoint_snapshot
from experiments.laya_weight_space.protocol import read_sealed, seal, write_json
from lgh.eval.compare import file_hash
from lgh.train.data import DatasetError

DECISION_PREFIXES = ('type_emb.', 'head.', 'scorer.')


def changed_elements(before: torch.Tensor, after: torch.Tensor) -> int:
    if before.shape != after.shape or before.dtype != after.dtype:
        raise DatasetError('tensor shape/dtype mismatch')
    a = before.contiguous().reshape(-1).view(torch.uint8).reshape(-1, before.element_size())
    b = after.contiguous().reshape(-1).view(torch.uint8).reshape(-1, after.element_size())
    return int(torch.count_nonzero((a != b).any(dim=1)))


def check_paths(base: Path, output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise DatasetError('output already exists; choose a new directory')
    if output.resolve().is_relative_to(base.resolve()):
        raise DatasetError('output must not be inside the base checkpoint')
    if base.is_symlink() or any(p.is_symlink() for p in base.rglob('*')):
        raise DatasetError('checkpoint symlinks are not supported')


def apply_patch(base: Path, replacements: Path, output: Path, *, expected_base_sha256: str,
                allowed_tensors: list[str], hypothesis: str, encoder_evidence: str | None = None) -> dict:
    check_paths(base, output)
    before = checkpoint_snapshot(base)
    if before['identity_sha256'] != expected_base_sha256:
        raise DatasetError('base checkpoint hash mismatch')
    if not hypothesis.strip() or not allowed_tensors or len(set(allowed_tensors)) != len(allowed_tensors):
        raise DatasetError('hypothesis and unique allowed tensor names are required')
    weights = load_file(str(base / 'model.safetensors'))
    payload_hash = file_hash(replacements)
    updates = load_file(str(replacements))
    if not updates or not set(updates) <= set(allowed_tensors) or not set(allowed_tensors) <= set(weights):
        raise DatasetError('unknown or undeclared tensor')
    for name in allowed_tensors:
        if not name.startswith(DECISION_PREFIXES):
            if not (name.startswith('encoder.') and encoder_evidence and encoder_evidence.strip()):
                raise DatasetError('forbidden tensor scope; encoder changes require recorded probe evidence')
    # Reject corrupt input even when the corrupt tensor is not being edited.
    if any(not torch.isfinite(value).all() for value in weights.values()):
        raise DatasetError('nonfinite base tensor')
    changes = {}
    for name, value in updates.items():
        original = weights[name]
        if (value.shape != original.shape or value.dtype != original.dtype
                or not value.is_floating_point() or not torch.isfinite(value).all()):
            raise DatasetError('invalid replacement shape, dtype or nonfinite value')
        delta = value.double() - original.double()
        changes[name] = {'shape': list(value.shape), 'dtype': str(value.dtype),
            'changed_parameters': changed_elements(original, value),
            'delta_l2': torch.linalg.vector_norm(delta).item(),
            'delta_linf': delta.abs().max().item(),
            'before_l2': torch.linalg.vector_norm(original.double()).item(),
            'after_l2': torch.linalg.vector_norm(value.double()).item()}
        weights[name] = value
    if file_hash(replacements) != payload_hash:
        raise DatasetError('replacement payload changed while reading')
    output.mkdir(parents=True, exist_ok=False)
    try:
        candidate = output / 'checkpoint'
        shutil.copytree(base, candidate)
        shutil.copyfile(replacements, output / 'replacements.safetensors')
        changed = sum(c['changed_parameters'] for c in changes.values())
        if changed:
            save_file(weights, str(candidate / 'model.safetensors'))
        saved = load_file(str(candidate / 'model.safetensors'))
        if set(saved) != set(weights) or any(changed_elements(saved[n], v) for n, v in weights.items()):
            raise DatasetError('saved tensor verification failed')
        after = checkpoint_snapshot(candidate)
        if (checkpoint_snapshot(base) != before
                or file_hash(output / 'replacements.safetensors') != payload_hash
                or any(after['files'].get(n) != sha for n, sha in before['files'].items()
                       if n != 'model.safetensors')):
            raise DatasetError('base, payload or non-weight checkpoint files changed')
        result = seal({'version': 1, 'kind': 'weight_space_patch', 'base': before,
            'candidate': after, 'replacement_sha256': payload_hash, 'hypothesis': hypothesis,
            'allowed_tensors': allowed_tensors, 'encoder_evidence': encoder_evidence,
            'changes': changes, 'changed_parameters': changed,
            'source_sha256': file_hash(Path(__file__)),
            'load_status': 'safetensors_verified; model reload requires probe smoke',
            'rollback': 'verified byte-for-byte copy of frozen base; no floating-point subtraction'})
        write_json(output / 'manifest.json', result)
        return result
    except BaseException as exc:
        write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__})
        raise


def restore(base: Path, patch_directory: Path, output: Path) -> dict:
    """Restore to a NEW directory, requiring the patch and both checkpoint identities."""
    check_paths(base, output)
    if output.resolve().is_relative_to(patch_directory.resolve()):
        raise DatasetError('restore output must not be inside patch directory')
    manifest = read_sealed(patch_directory / 'manifest.json')
    if manifest.get('kind') != 'weight_space_patch' or manifest.get('version') != 1:
        raise DatasetError('unsupported patch manifest')
    before = checkpoint_snapshot(base)
    if before['identity_sha256'] != manifest['base']['identity_sha256']:
        raise DatasetError('base checkpoint hash mismatch')
    if (checkpoint_snapshot(patch_directory / 'checkpoint')['identity_sha256']
            != manifest['candidate']['identity_sha256']
            or file_hash(patch_directory / 'replacements.safetensors') != manifest['replacement_sha256']):
        raise DatasetError('candidate or replacement payload hash mismatch')
    shutil.copytree(base, output)
    result = checkpoint_snapshot(output)
    if result['files'] != before['files'] or checkpoint_snapshot(base) != before:
        raise DatasetError('restoration verification failed')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    apply = sub.add_parser('apply')
    for name in ('base', 'replacements', 'output'):
        apply.add_argument(f'--{name}', type=Path, required=True)
    apply.add_argument('--expected-base-sha256', required=True)
    apply.add_argument('--allow-tensor', action='append', required=True)
    apply.add_argument('--hypothesis', required=True)
    apply.add_argument('--encoder-evidence')
    undo = sub.add_parser('restore')
    for name in ('base', 'patch-directory', 'output'):
        undo.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'apply':
        result = apply_patch(args.base, args.replacements, args.output,
            expected_base_sha256=args.expected_base_sha256, allowed_tensors=args.allow_tensor,
            hypothesis=args.hypothesis, encoder_evidence=args.encoder_evidence)
        print(json.dumps({'manifest_sha256': result['sha256'], 'changed_parameters': result['changed_parameters']}))
    else:
        result = restore(args.base, args.patch_directory, args.output)
        print(json.dumps({'restored_checkpoint_sha256': result['identity_sha256']}))


if __name__ == '__main__':
    main()
