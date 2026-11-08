"""WS-05: one predeclared B/D training run, shared calibration, open development only."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import gc
import json
from pathlib import Path
import shutil
import time

from experiments.laya_weight_space.evaluate import paired_metrics
from experiments.laya_weight_space.partitions import audit_splits
from experiments.laya_weight_space.preflight import (
    checkpoint_snapshot, configuration_snapshot, current_session, package_versions,
)
from experiments.laya_weight_space.protocol import read_protocol, read_sealed, seal, validate_inputs, write_json
from lgh.config.models import GuardrailConfig
from lgh.eval.backend_contract import validate_answers
from lgh.eval.compare import detailed_metrics, file_hash
from lgh.ids import utc_now_iso
from lgh.laya.normalize import normalize_assessment
from lgh.policy.reducer import reduce_decision
from lgh.schema.rules import RuleDisposition, RuleResult
from lgh.train.data import DatasetError

PARTITIONS = ('train', 'development', 'validation', 'calibration')


def read_training_inputs(protocol: Path, directory: Path) -> tuple[dict, dict, dict]:
    p, manifest = read_protocol(protocol), read_sealed(directory / 'manifest.json')
    if (manifest.get('version') != 1 or manifest.get('kind') != 'weight_space_partitions'
            or not manifest.get('development_ready') or manifest['protocol_sha256'] != p['sha256']):
        raise DatasetError('partitions are not ready or bound to this protocol')
    required = {f'{name}/{file}' for name in PARTITIONS for file in ('dataset.jsonl', 'replay.jsonl')}
    if not required <= set(manifest['files']):
        raise DatasetError('missing explicit partitions')
    for name, expected in manifest['files'].items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or file_hash(path) != expected:
            raise DatasetError('partition file hash mismatch')
    for source, expected in manifest['source_hashes'].items():
        if file_hash(Path(source)) != expected:
            raise DatasetError('partition source hash mismatch')
    base = checkpoint_snapshot(Path(p['base']['path']))
    if (base['identity_sha256'] != p['base']['checkpoint_sha256']
            or base['files']['model.safetensors'] != p['base']['weights_sha256']):
        raise DatasetError('base checkpoint differs from frozen protocol')
    splits = {name: validate_inputs(directory / name / 'dataset.jsonl',
                                   directory / name / 'replay.jsonl', p) for name in PARTITIONS}
    audit_splits({name: rows for name, (rows, _) in splits.items()}, [])
    return p, manifest, splits


def copy_with_temperatures(base: Path, output: Path, temperatures: dict) -> None:
    """Copy original bytes, changing only the inference temperature configuration."""
    shutil.copytree(base, output)
    path = output / 'rl_agent_config.json'
    cfg = json.loads(path.read_text())
    cfg['temperature_by_options'] = {**cfg.get('temperature_by_options', {}), **temperatures}
    path.write_text(json.dumps(cfg, indent=2) + '\n')
    before, after = checkpoint_snapshot(base), checkpoint_snapshot(output)
    if any(after['files'].get(k) != v for k, v in before['files'].items() if k != 'rl_agent_config.json'):
        raise DatasetError('calibration changed files other than temperature configuration')


def compare_development(p: dict, rows: list, cases: list, predictions: dict) -> tuple[dict, dict]:
    config = GuardrailConfig.model_validate(p['config'])
    routed = {}
    pass_rules = RuleResult(matched=[], disposition=RuleDisposition.PASS)
    for arm, predicted in predictions.items():
        routed[arm] = []
        for row, case, answer in zip(rows, cases, predicted, strict=True):
            validate_answers(answer, row['questions'])
            assessment = normalize_assessment({'answers': answer}, model=arm, latency_ms=0,
                                              temperatures=config.laya.temperatures)
            routed[arm].append({
                'trace_id': row['trace_id'], 'group_id': row['group_id'],
                'reference': case.reference.model_dump(mode='json'),
                'model_dependent': case.rules.disposition == RuleDisposition.PASS,
                'policy_decision': reduce_decision(case.rules, assessment, config.laya.thresholds).value,
                'semantic_only_decision': reduce_decision(pass_rules, assessment, config.laya.thresholds).value,
            })
    pairs = {}
    for before, after in [('B', 'D'), ('B_operational', 'B'), ('B_operational', 'D'),
                          ('B_unit_temperature', 'D_unit_temperature'),
                          ('B_unit_temperature', 'B'), ('D_unit_temperature', 'D')]:
        pairs[f'{before}_to_{after}'] = {}
        for subset, predicate, field in [
            ('all', lambda r: True, 'policy_decision'),
            ('rule_pass', lambda r: r['model_dependent'], 'policy_decision'),
            ('rule_controlled', lambda r: not r['model_dependent'], 'policy_decision'),
            ('semantic_only', lambda r: True, 'semantic_only_decision'),
        ]:
            pairs[f'{before}_to_{after}'][subset] = paired_metrics(
                [r for r in routed[before] if predicate(r)], [r for r in routed[after] if predicate(r)], field)
    return {'purpose': 'open_development_only', 'rows': len(rows),
            'models': {arm: detailed_metrics(predicted, rows) for arm, predicted in predictions.items()},
            'pairs': pairs, 'selection': 'not_evaluated_for_promotion',
            'scope': p['routing_scope']}, routed


def execute_models(p: dict, directory: Path, output: Path, splits: dict, settings, device: str, log) -> dict:
    import laya
    import torch
    from lgh.train.evaluate import fit_bucket_temperatures
    from lgh.train.loop import encode_row, temperature_samples
    from lgh.train.runner import run_training

    if not device.startswith('cuda') or not torch.cuda.is_available():
        raise RuntimeError('WS-05 requires CUDA; no silent CPU fallback')
    torch.cuda.reset_peak_memory_stats()
    base = Path(p['base']['path'])
    rows, cases = splits['development']
    cal_rows = splits['calibration'][0]
    log('training D from frozen B; checkpoint selection uses validation loss only')
    training_started = time.monotonic()
    training = run_training(directory / 'train/dataset.jsonl', output / 'D', str(base), device, settings, log,
                            validation=directory / 'validation/dataset.jsonl',
                            calibration=directory / 'calibration/dataset.jsonl')
    training_seconds = time.monotonic() - training_started
    d_snapshot = checkpoint_snapshot(output / 'D')
    gc.collect()
    torch.cuda.empty_cache()
    predictions, identities = {}, {}

    def load(path):
        agent = laya.load(str(path), device=device)
        if agent.device.type != 'cuda':
            raise RuntimeError('Laya fell back from CUDA')
        agent.model.eval()
        return agent

    def collect(arm, agent, snapshot, calibration):
        log(f'collecting {arm}: {len(rows)} development cases, seven questions each')
        predictions[arm] = [validate_answers(agent.predict(r['state'], r['questions'])['answers'],
                                            r['questions']) for r in rows]
        identities[arm] = {'path': snapshot['path'], 'checkpoint_sha256': snapshot['identity_sha256'],
            'weights_sha256': snapshot['files']['model.safetensors'],
            'parent_weights_sha256': p['base']['weights_sha256'] if arm.startswith('D') else None,
            'calibration': calibration, 'effective_temperatures': dict(agent.temperature_by_options),
            'calibration_dataset_sha256': file_hash(directory / 'calibration/dataset.jsonl')
                                         if calibration == 'shared_holdout' else None,
            'in_memory_temperature_override': calibration == 'unit_temperature'}

    base_snapshot = checkpoint_snapshot(base)
    agent = load(base)
    collect('B_operational', agent, base_snapshot, 'original')
    log('fitting B temperatures on the same separate calibration data as D')
    temperatures = fit_bucket_temperatures(temperature_samples(agent, [encode_row(agent, r) for r in cal_rows]))
    copy_with_temperatures(base, output / 'B', temperatures)
    agent.temperature_by_options = {key: 1.0 for key in temperatures}
    collect('B_unit_temperature', agent, base_snapshot, 'unit_temperature')
    del agent
    gc.collect()
    torch.cuda.empty_cache()
    agent = load(output / 'B')
    collect('B', agent, checkpoint_snapshot(output / 'B'), 'shared_holdout')
    del agent
    gc.collect()
    torch.cuda.empty_cache()
    agent = load(output / 'D')
    collect('D', agent, d_snapshot, 'shared_holdout')
    agent.temperature_by_options = {key: 1.0 for key in temperatures}
    collect('D_unit_temperature', agent, d_snapshot, 'unit_temperature')
    del agent
    gc.collect()
    torch.cuda.empty_cache()
    if checkpoint_snapshot(output / 'D') != d_snapshot or checkpoint_snapshot(base) != base_snapshot:
        raise DatasetError('checkpoint changed during inference/calibration')
    report, routed = compare_development(p, rows, cases, predictions)
    write_json(output / 'predictions.json', {'protocol_sha256': p['sha256'], 'models': identities,
        'predictions': {arm: [{'trace_id': r['trace_id'], 'answers': answer}
                             for r, answer in zip(rows, answers, strict=True)]
                        for arm, answers in predictions.items()}})
    write_json(output / 'routing.json', routed)
    epochs = len(training['history']) - 1
    return {**report, 'identities': identities, 'history': training['history'],
        'selected_epoch': min(training['history'], key=lambda h: h['val_loss'])['epoch'],
        'temperatures': {'B': temperatures, 'D': training['temperatures']},
        'training_seconds': training_seconds,
        'gpu': {'name': torch.cuda.get_device_name(), 'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                'peak_reserved_bytes': torch.cuda.max_memory_reserved()},
        'work_counts': {'training_case_passes': epochs * len(splits['train'][0]),
            'validation_loss_case_passes': (epochs + 1) * len(splits['validation'][0]),
            'validation_prediction_cases': 2 * len(splits['validation'][0]),
            'calibration_case_passes': 2 * len(cal_rows),
            'development_prediction_cases': len(predictions) * len(rows), 'questions_per_case': 7,
            'weight_edit_proposals': 0, 'final_test_cases': 0},
        'D_for_DW': {'path': d_snapshot['path'], 'checkpoint_sha256': d_snapshot['identity_sha256'],
                     'weights_sha256': d_snapshot['files']['model.safetensors']}}


def run(protocol: Path, directory: Path, output: Path, settings, device: str) -> dict:
    if output.exists():
        raise DatasetError('output already exists; use a new attempt directory')
    p, manifest, splits = read_training_inputs(protocol, directory)
    if any(output.resolve().is_relative_to(path.resolve())
           for path in (directory, protocol.parent, Path(p['base']['path']))):
        raise DatasetError('output must not be inside frozen inputs or base checkpoint')
    astra = current_session()
    if astra.get('status') != 'verified':
        raise DatasetError('verified Astra session required; no silent model substitution')
    config = configuration_snapshot(Path.cwd())
    started, clock = utc_now_iso(), time.monotonic()
    plan = seal({'version': 1, 'task': 'WS-05', 'purpose': 'open_development_only',
        'started_at': started, 'protocol_sha256': p['sha256'], 'partitions_sha256': manifest['sha256'],
        'base': p['base'], 'settings': asdict(settings), 'device': device, 'astra': astra,
        'packages': package_versions(), 'attempt_budget': 1, 'new_api_spend_limit_usd': 0,
        'weight_selection': 'lowest validation loss including epoch zero; no development-based retry',
        'calibration': p['calibration'], 'test_cases': 0,
        'source_sha256': file_hash(Path(__file__)),
        'reproducibility': 'seed and runtime recorded; bitwise CUDA reproducibility not asserted'})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'plan.json', plan)

    def log(message):
        with (output / 'journal.jsonl').open('a') as stream:
            stream.write(json.dumps({'time': utc_now_iso(), 'message': message}) + '\n')
        print(message, flush=True)

    try:
        log('started')
        result = execute_models(p, directory, output, splits, settings, device, log)
        after_p, after_manifest, _ = read_training_inputs(protocol, directory)
        if (after_p != p or after_manifest != manifest or config != configuration_snapshot(Path.cwd())
                or file_hash(Path(__file__)) != plan['source_sha256']):
            raise DatasetError('frozen inputs, source or live configuration changed during run')
        result.update(plan_sha256=plan['sha256'], protocol_sha256=p['sha256'],
            partitions_sha256=manifest['sha256'], finished_at=utc_now_iso(),
            elapsed_seconds=time.monotonic() - clock, status='complete_open_development',
            cost={'new_api_requests': 0, 'new_api_spend_usd': 0, 'codex_session_cost_usd': None,
                  'local_compute_cost_usd': None},
            limitations=['Synthetic author-reviewed data; no independent human final test.',
                         'No access isolation; validation/calibration are open development evidence.',
                         'Single seed and small class support; no production or causal-mechanism claim.',
                         'No rule, policy, configured model or recorded action was changed/executed.'])
        write_json(output / 'report.json', seal(result))
        log('complete_open_development')
        write_json(output / 'manifest.json', seal({'version': 1, 'task': 'WS-05',
            'status': result['status'], 'plan_sha256': plan['sha256'], 'D_for_DW': result['D_for_DW'],
            'files': {str(path.relative_to(output)): file_hash(path)
                      for path in sorted(output.rglob('*')) if path.is_file()}}))
        return result
    except BaseException as exc:
        log(f'failed: {type(exc).__name__}: {exc}')
        write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__,
            'error': str(exc), 'elapsed_seconds': time.monotonic() - clock, 'plan_sha256': plan['sha256']})
        raise


def main() -> None:
    from lgh.train.loop import TrainSettings
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('protocol', 'partitions', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    result = run(args.protocol, args.partitions, args.output, TrainSettings(), args.device)
    print(json.dumps({'status': result['status'], 'selected_epoch': result['selected_epoch'],
                      'report': str(args.output / 'report.json')}))


if __name__ == '__main__':
    main()
