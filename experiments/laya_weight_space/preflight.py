"""Read-only WS-01 inventory and tiny tensor probe; no model loading or API calls."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform

from lgh.config.loader import load_config
from lgh.eval.backend_setup import gpu_snapshot
from lgh.eval.compare import file_hash
from lgh.ids import utc_now_iso
from lgh.paths import user_config_path, user_rules_path

REQUIRED_FILES = (
    'model.safetensors', 'rl_agent_config.json', 'config.json',
    'encoder/config.json', 'tokenizer/tokenizer.json', 'tokenizer/tokenizer_config.json',
)
ASTRA_MODEL = 'gpt-6-astra'


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def checkpoint_snapshot(path: Path) -> dict:
    path = path.resolve()
    missing = [name for name in REQUIRED_FILES if not (path / name).is_file()]
    if missing:
        raise ValueError(f'missing checkpoint files in {path}: {missing}')
    files = {str(p.relative_to(path)): file_hash(p) for p in sorted(path.rglob('*')) if p.is_file()}
    cfg = json.loads((path / 'rl_agent_config.json').read_text())
    return {'path': str(path), 'files': files, 'identity_sha256': digest(files),
            'training': cfg.get('lgh_training', {}),
            'temperatures': cfg.get('temperature_by_options', {}),
            'encoder': json.loads((path / 'encoder/config.json').read_text())}


def training_history(metadata: dict, legacy_export: Path | None) -> dict:
    declared = dict(metadata.get('datasets', {}))
    if 'train' not in declared:
        declared['train'] = {'path': str(legacy_export) if legacy_export else None,
                             'sha256': metadata.get('dataset_sha256')}
    datasets = {}
    for name, item in declared.items():
        path = Path(item['path']) if item.get('path') else None
        actual = file_hash(path) if path and path.is_file() else None
        expected = item.get('sha256')
        status = ('missing' if actual is None else 'unverified' if not expected
                  else 'verified' if actual == expected else 'hash_mismatch')
        datasets[name] = {'path': str(path) if path else None, 'expected_sha256': expected,
                          'actual_sha256': actual, 'status': status}
    return {'datasets': datasets, 'upstream_base': metadata.get('base'),
            'upstream_pretraining': 'unknown',
            'partition_provenance': 'separate_declared_files' if metadata.get('datasets')
            else 'legacy_full_export; validation/calibration separation not established'}


def session_evidence(path: Path, thread_id: str | None) -> dict:
    """Extract only identity fields; never copy prompts, outputs, auth or user config."""
    if not thread_id:
        return {'status': 'thread_unverified'}
    session_id = None
    latest = None
    # The active log can be appended while the tool runs. Ignore a partial final line.
    with path.open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                break
            record = json.loads(line)
            if record.get('type') == 'session_meta':
                session_id = record['payload'].get('id')
            if record.get('type') == 'turn_context':
                latest = record['payload']
    if session_id != thread_id:
        return {'status': 'thread_mismatch'}
    if latest is None:
        return {'status': 'no_turn_context'}
    selected = {key: latest.get(key) for key in ('model', 'effort', 'turn_id')}
    return {**selected, 'thread_id': thread_id, 'source': str(path.resolve()),
            'record_sha256': digest(selected),
            'status': 'verified' if selected['model'] == ASTRA_MODEL else 'model_mismatch',
            'identity_scope': 'Codex recorded turn model; not a pinned server model revision'}


def current_session() -> dict:
    thread_id = os.environ.get('CODEX_THREAD_ID')
    if not thread_id:
        return {'status': 'thread_unverified'}
    root = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'sessions'
    matches = list(root.rglob(f'*{thread_id}*.jsonl'))
    if len(matches) != 1:
        return {'status': 'not_found' if not matches else 'ambiguous'}
    return session_evidence(matches[0], thread_id)


def configuration_snapshot(cwd: Path) -> dict:
    cfg = load_config(repo_root=cwd)
    paths = [user_config_path(), user_rules_path(), cwd / '.guardrail/config.yaml',
             cwd / '.guardrail/rules.yaml', cwd / 'src/lgh/laya/questions_v0_1.yaml']
    return {'configured_model': cfg.laya.model, 'configured_device': cfg.laya.device,
            'daemon_url': cfg.laya.daemon_url, 'normalization_temperatures': cfg.laya.temperatures,
            'effective_sha256': digest(cfg.model_dump(mode='json')),
            'files': {str(p.resolve()): file_hash(p) if p.is_file() else None for p in paths},
            'scope': 'configuration on disk; active daemon identity not measured'}


def tensor_probe() -> dict:
    """Fixed 2x2 toy weights, never Laya weights. CUDA failure stays explicit."""
    try:
        import torch
    except ImportError:
        return {'cpu': {'status': 'unavailable'}, 'cuda': {'status': 'unavailable'}}

    def compute(device: str) -> dict:
        try:
            with torch.no_grad():
                weights = torch.tensor([[1., 2.], [3., 4.]], device=device)
                original = weights.clone()
                output = weights @ torch.tensor([[1.], [2.]], device=device)
                passed = torch.equal(weights, original) and torch.equal(
                    output, torch.tensor([[5.], [11.]], device=device))
            return {'status': 'passed' if passed else 'failed', 'output': output.cpu().tolist(),
                    'device': str(weights.device), 'dtype': str(weights.dtype)}
        except RuntimeError:
            return {'status': 'failed', 'reason': 'tensor computation failed', 'device': device}

    result = {'cpu': compute('cpu'), 'torch_cuda_build': torch.version.cuda,
              'cuda': {'status': 'unavailable'}}
    if torch.cuda.is_available():
        result['cuda'] = compute('cuda:0')
    return result


def package_versions() -> dict:
    result = {'python': platform.python_version()}
    for name in ('laya', 'torch', 'transformers', 'safetensors', 'numpy'):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def run_preflight(output: Path, *, cwd: Path, base_training: Path | None = None,
                  reference_checkpoint: Path | None = None) -> dict:
    if output.exists():
        raise ValueError(f'{output} already exists; choose a new output directory')
    config = configuration_snapshot(cwd)
    base_path = Path(config['configured_model'])
    checkpoints = {'base': base_path}
    if reference_checkpoint:
        checkpoints['historical_candidate_02'] = reference_checkpoint
    if any(output.resolve().is_relative_to(p.resolve()) for p in checkpoints.values()):
        raise ValueError('output must not be inside checkpoint')
    started = utc_now_iso()
    before = {name: checkpoint_snapshot(path) for name, path in checkpoints.items()}
    histories = {name: training_history(item['training'], base_training if name == 'base' else None)
                 for name, item in before.items()}
    astra = current_session()
    probe = tensor_probe()
    gpu = gpu_snapshot()
    after = {name: checkpoint_snapshot(path) for name, path in checkpoints.items()}
    after_histories = {name: training_history(item['training'], base_training if name == 'base' else None)
                       for name, item in after.items()}
    after_config = configuration_snapshot(cwd)
    unchanged = before == after and config == after_config and histories == after_histories
    pending = []
    packages = package_versions()
    if any(not packages.get(name) for name in ('laya', 'torch', 'transformers', 'safetensors', 'numpy')):
        pending.append('runtime_packages')
    if not unchanged:
        pending.append('inputs_changed_during_preflight')
    if astra.get('status') != 'verified':
        pending.append('astra_session')
    for device in ('cpu', 'cuda'):
        if probe[device]['status'] != 'passed':
            pending.append(f'{device}_probe')
    if not gpu.get('observed'):
        pending.append('gpu_telemetry')
    for name, history in histories.items():
        if any(d['status'] != 'verified' for d in history['datasets'].values()):
            pending.append(f'{name}_training_exports')
    for name, item in before.items():
        if name != 'base':
            parent = item['training'].get('base_identity', {})
            if not parent or any(before['base']['files'].get(k) != v for k, v in parent.items()):
                pending.append(f'{name}_parent_identity')
    source_paths = [Path(__file__).resolve(), cwd / 'pyproject.toml', cwd / 'uv.lock',
                    *sorted((cwd / 'src/lgh').rglob('*.py'))]
    report = {
        'version': 1, 'task': 'WS-01', 'status': 'pending' if pending else 'complete',
        'started_at': started, 'finished_at': utc_now_iso(), 'pending': pending,
        **before, 'configuration': config, 'histories': histories,
        'packages': packages, 'gpu': gpu, 'tensor_probe': probe, 'astra': astra,
        'integrity': {'unchanged': unchanged, 'after_identities': {
            name: item['identity_sha256'] for name, item in after.items()},
            'configuration_after': after_config, 'histories_after': after_histories},
        'source_hashes': {str(p): file_hash(p) for p in source_paths if p.is_file()},
        'budget': {'route': 'existing_codex_session_local_tools', 'new_api_requests': 0,
                   'new_api_spend_limit_usd': 0, 'codex_session_cost_usd': None,
                   'toy_probe_invocations': 1, 'laya_forward_passes': 0,
                   'weight_editing_runs': 0},
        'experiment_ready': False,
        'next_prerequisites': ['WS-02 protocol', 'WS-03/04 reviewed partitions and test isolation'],
        'limits': ['No model load or Laya inference; toy CUDA success does not establish training capacity.',
                   'Checkpoint hashes detect drift; they do not provide OS-level write isolation.',
                   'Astra identity is local session evidence, not server attestation or API entitlement.',
                   'New test isolation is not established in this workspace.',
                   'Unknown upstream data and legacy validation/calibration overlap remain limitations.'],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-training', type=Path)
    parser.add_argument('--reference-checkpoint', type=Path)
    args = parser.parse_args()
    report = run_preflight(args.output, cwd=Path.cwd(), base_training=args.base_training,
                           reference_checkpoint=args.reference_checkpoint)
    print(json.dumps({'status': report['status'], 'pending': report['pending'],
                      'manifest': str(args.output / 'manifest.json')}))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
