"""WS-06/07: real CUDA observations, zero patch and exact restoration on development cases."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import shutil
import time

from safetensors.torch import load_file, save_file
import torch

from experiments.laya_weight_space.budget import Budget
from experiments.laya_weight_space.patch import apply_patch, check_paths, restore
from experiments.laya_weight_space.preflight import (
    checkpoint_snapshot, configuration_snapshot, current_session, package_versions,
)
from experiments.laya_weight_space.probe import run_probe, tensor_fingerprint
from experiments.laya_weight_space.protocol import read_protocol, read_sealed, seal, validate_inputs, write_json
from lgh.eval.compare import file_hash
from lgh.ids import utc_now_iso
from lgh.train.data import DatasetError


def development_inputs(protocol: dict, directory: Path) -> tuple[dict, list, list]:
    manifest = read_sealed(directory / 'manifest.json')
    if (manifest.get('kind') != 'weight_space_partitions' or not manifest.get('development_ready')
            or manifest['protocol_sha256'] != protocol['sha256']):
        raise DatasetError('development partitions/protocol mismatch')
    for name in ('development/dataset.jsonl', 'development/replay.jsonl'):
        if file_hash(directory / name) != manifest['files'].get(name):
            raise DatasetError('development file hash mismatch')
    rows, cases = validate_inputs(directory / 'development/dataset.jsonl', directory / 'development/replay.jsonl', protocol)
    return manifest, rows, cases


def load_copy(source: Path, runtime: Path, device: str):
    import laya
    check_paths(source, runtime)
    before = checkpoint_snapshot(source)
    shutil.copytree(source, runtime)
    agent = laya.load(str(runtime.resolve()), device=device)
    agent.model.eval()
    if agent.device.type != 'cuda':
        raise DatasetError('CUDA required; runtime fell back to CPU')
    expected = tensor_fingerprint(load_file(str(source / 'model.safetensors')))
    if (tensor_fingerprint(agent.model.state_dict()) != expected
            or checkpoint_snapshot(runtime)['files'] != before['files']
            or checkpoint_snapshot(source) != before):
        raise DatasetError('loaded model or checkpoint copy differs from source')
    return agent


def run(protocol_path: Path, directory: Path, output: Path, *, count: int = 2, device: str = 'cuda',
        budget_path: Path | None = None) -> dict:
    p = read_protocol(protocol_path)
    base = Path(p['base']['path'])
    check_paths(base, output)
    if any(output.resolve().is_relative_to(path.resolve()) for path in (directory, protocol_path.parent)):
        raise DatasetError('output must not be inside frozen inputs')
    manifest, rows, cases = development_inputs(p, directory)
    if not 1 <= count <= min(64, len(rows)):
        raise DatasetError('invalid smoke case count')
    rows, cases = rows[:count], cases[:count]
    before = checkpoint_snapshot(base)
    if (before['identity_sha256'] != p['base']['checkpoint_sha256']
            or before['files']['model.safetensors'] != p['base']['weights_sha256']):
        raise DatasetError('frozen base changed')
    session = current_session()
    if session.get('status') != 'verified':
        raise DatasetError('verified Astra session required for real development observations')
    config = configuration_snapshot(Path.cwd())
    ledger_path = budget_path or output / 'budget.json'
    if any(ledger_path.resolve().is_relative_to(path.resolve()) for path in (base, directory, protocol_path.parent)):
        raise DatasetError('budget must not be inside frozen inputs')
    if ledger_path.exists():
        budget = Budget(ledger_path)
        prior = budget.snapshot()
        if (prior['protocol_sha256'] != p['sha256'] or prior['parent_sha256'] != before['identity_sha256']
                or prior['arm'] != 'W' or prior['purpose'] != 'search'):
            raise DatasetError('budget parent/protocol/arm/purpose mismatch')
    else:
        budget, prior = None, None
    output.mkdir(parents=True, exist_ok=False)
    sources = {name: file_hash(Path(__file__).with_name(name))
               for name in ('budget.py', 'probe.py', 'patch.py', 'smoke.py')}
    plan = seal({'task': ['WS-06', 'WS-07'], 'started_at': utc_now_iso(),
        'purpose': 'open_development_tool_verification', 'protocol_sha256': p['sha256'],
        'partitions_sha256': manifest['sha256'], 'base': before, 'session': session,
        'packages': package_versions(), 'source_hashes': sources,
        'case_ids': [r['trace_id'] for r in rows], 'device': device,
        'declared_evaluation_calls': 5, 'declared_case_exposures': 5 * count,
        'probability_absolute_tolerance': 0.0,
        'budget_path': str(ledger_path.resolve()), 'prior_budget': prior,
        'accounting': 'All five observations charge W search budget. WS-08 must reuse this ledger.',
        'patch_scope': 'zero replacement of scorer.3.bias only; infrastructure check, no W proposal',
        'cost': {'new_api_requests': 0, 'new_api_spend_usd': 0,
                 'session_cost_usd': None, 'local_compute_cost_usd': None}})
    write_json(output / 'plan.json', plan)
    if budget is None:
        budget = Budget.create(ledger_path, protocol_sha256=p['sha256'],
                               parent_sha256=before['identity_sha256'], arm='W')
    start = time.monotonic()
    try:
        if not device.startswith('cuda') or not torch.cuda.is_available():
            raise DatasetError('CUDA unavailable; no silent CPU fallback')
        torch.cuda.reset_peak_memory_stats()
        agent = load_copy(base, output / 'base-runtime', device)
        results = {}
        for name, modules in [('before', []), ('observed', ['type_emb', 'scorer.3']), ('after', [])]:
            print(f'collecting {name}: {count} cases', flush=True)
            results[name] = run_probe(agent, rows, cases, p, budget,
                tensor_names=['scorer.3.weight', 'scorer.3.bias'], module_names=modules)
            write_json(output / f'{name}.json', seal(results[name]))
        del agent
        gc.collect()
        torch.cuda.empty_cache()
        weights = load_file(str(base / 'model.safetensors'))
        save_file({'scorer.3.bias': weights['scorer.3.bias'].clone()}, str(output / 'zero.safetensors'))
        del weights
        patch = apply_patch(base, output / 'zero.safetensors', output / 'zero-patch',
            expected_base_sha256=before['identity_sha256'], allowed_tensors=['scorer.3.bias'],
            hypothesis='Infrastructure zero patch must preserve tensors and predictions exactly.')
        restore(base, output / 'zero-patch', output / 'restored')
        for name, source in [('zero', output / 'zero-patch/checkpoint'), ('restored', output / 'restored')]:
            print(f'collecting {name}: {count} cases', flush=True)
            agent = load_copy(source, output / f'{name}-runtime', device)
            results[name] = run_probe(agent, rows, cases, p, budget, tensor_names=[], module_names=[])
            write_json(output / f'{name}.json', seal(results[name]))
            del agent
            gc.collect()
            torch.cuda.empty_cache()
        expected = [r['answers'] for r in results['before']['cases']]
        if any([r['answers'] for r in result['cases']] != expected for result in results.values()):
            raise DatasetError('observation/zero/restore changed predictions at declared zero tolerance')
        if (checkpoint_snapshot(base) != before or configuration_snapshot(Path.cwd()) != config
                or read_protocol(protocol_path) != p or development_inputs(p, directory)[0] != manifest
                or any(file_hash(Path(__file__).with_name(n)) != sha for n, sha in sources.items())):
            raise DatasetError('base, configuration, protocol, data or source changed during smoke')
        report = seal({'status': 'complete_open_development', 'plan_sha256': plan['sha256'],
            'elapsed_seconds': time.monotonic() - start, 'identical_predictions': True,
            'identical_tensor_fingerprints': len({r['tensor_sha256'] for r in results.values()}) == 1,
            'base_and_config_unchanged': True, 'zero_patch_sha256': patch['sha256'],
            'budget': budget.snapshot(), 'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
            'gpu': torch.cuda.get_device_name(), 'test_cases': 0,
            'limitations': ['Open synthetic development only; no isolated human test.',
                'This verifies tools, not model improvement or a causal mechanism.',
                'No candidate activation; no recorded actions executed.']})
        write_json(output / 'report.json', report)
        write_json(output / 'budget-snapshot.json', budget.snapshot())
        write_json(output / 'manifest.json', seal({'task': ['WS-06', 'WS-07'],
            'status': report['status'], 'live_budget_path': str(ledger_path.resolve()),
            'files': {str(path.relative_to(output)): file_hash(path)
                for path in sorted(output.rglob('*')) if path.is_file() and path.suffix != '.lock'
                and path.resolve() != ledger_path.resolve()}}))
        return report
    except BaseException as exc:
        write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__,
            'elapsed_seconds': time.monotonic() - start, 'budget': budget.snapshot()})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('protocol', 'partitions', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--cases', type=int, default=2)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--budget', type=Path, help='Existing W ledger for continuation; never resets its counters')
    args = parser.parse_args()
    result = run(args.protocol, args.partitions, args.output, count=args.cases, device=args.device,
                 budget_path=args.budget)
    print(json.dumps({'status': result['status'], 'report': str(args.output / 'report.json')}))


if __name__ == '__main__':
    main()
