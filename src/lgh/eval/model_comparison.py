"""Model-only collection when historical action-replay context is unavailable.

No rules, policy, reviewers or commands run. References stay local; repetitions
measure timing and answer stability, while quality uses repetition zero only.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from lgh.eval.backend_report import latency_summary
from lgh.eval.backend_setup import gpu_snapshot
from lgh.eval.backends import HttpBackend
from lgh.eval.compare import detailed_metrics, file_hash, read_dataset, state_hash
from lgh.eval.compare_backends import (
    audit_backend, evaluator_fingerprint, read_experiment, write_json, write_rows,
)
from lgh.ids import utc_now_iso
from lgh.laya.questions import load_questions
from lgh.train.data import DatasetError
from lgh.eval.backend_contract import validate_answers

ARTIFACTS = ('dataset.jsonl', 'experiment.json', 'predictions.jsonl')
PROTOCOL = 'model-only-v1'


def _questions(rows):
    expected = load_questions()
    signature = lambda q: [(k, v['type'], list(v.get('criteria', {}))) for k, v in q.items()]
    if any(r['questions'] != expected or signature(r['questions']) != signature(expected) for r in rows):
        raise DatasetError('dataset must use the exact v0.1 questions and option order')


def collect_model_pass(dataset: Path, experiment_path: Path, backend: str, output: Path,
                       *, timeout: float = 60, log=print) -> dict:
    if output.exists():
        raise DatasetError(f'{output} already exists; use a fresh output directory')
    experiment = read_experiment(experiment_path)
    if experiment.purpose != 'benchmark':
        raise DatasetError('model-only collection requires real-model benchmark endpoints')
    rows = read_dataset(dataset)
    _questions(rows)
    spec = experiment.backends[backend]
    audit = audit_backend(rows, spec)
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / 'dataset.jsonl', rows)
    write_json(output / 'experiment.json', experiment.model_dump(mode='json'))
    write_rows(output / 'predictions.jsonl', [])
    manifest = {
        'protocol': PROTOCOL, 'comparison_kind': 'model_only', 'status': 'incomplete',
        'backend': backend, 'required_backends': experiment.backend_names(), 'rows': len(rows),
        'evaluator_sha256': evaluator_fingerprint(), 'audit': audit,
        'source_dataset_sha256': file_hash(dataset), 'source_experiment_sha256': file_hash(experiment_path),
        'dataset_sha256': file_hash(output / 'dataset.jsonl'),
        'experiment_sha256': file_hash(output / 'experiment.json'),
        'declared_hardware': experiment.hardware, 'gpu_before': gpu_snapshot(),
        'timing': {'repetitions': experiment.repetitions, 'warmup': experiment.warmup,
                   'conditions': 'first_observed means repetition zero; repeated_request means later passes',
                   'cache_note': 'Pass labels do not establish cache misses/hits or cold startup.'},
    }
    write_json(output / 'manifest.json', manifest)
    try:
        manifest['collection_started_at'] = utc_now_iso()
        client = HttpBackend(spec, timeout=timeout)
        manifest['identity_before'] = client.identity()
        warmup = deepcopy(rows[0]['state'])
        hashes = {state_hash(r) for r in rows}
        suffix = 0
        while state_hash({'state': warmup}) in hashes:
            warmup['goal'] = rows[0]['state']['goal'] + f' [excluded model-only warmup {suffix}]'
            suffix += 1
        for _ in range(experiment.warmup):
            client.predict(warmup, rows[0]['questions'])
        for repetition in range(experiment.repetitions):
            for index, row in enumerate(rows, 1):
                prediction = client.predict(row['state'], row['questions'])
                validate_answers(prediction['answers'], row['questions'])
                sample = {'trace_id': row['trace_id'], 'backend': backend, 'repetition': repetition,
                          'condition': 'first_observed' if repetition == 0 else 'repeated_request',
                          **prediction}
                with (output / 'predictions.jsonl').open('a') as stream:
                    stream.write(json.dumps(sample, allow_nan=False) + '\n')
                if index % 25 == 0 or index == len(rows):
                    log(f'{backend}: pass {repetition + 1}/{experiment.repetitions}, {index}/{len(rows)}')
        manifest['identity_after'] = client.identity()
        for key in ('model', 'run', 'base', 'device', 'dtype', 'backend', 'temperature', 'truncate_states'):
            if manifest['identity_before']['observed'].get(key) != manifest['identity_after']['observed'].get(key):
                raise DatasetError(f'backend identity changed during collection: {key}')
        if (evaluator_fingerprint() != manifest['evaluator_sha256']
                or file_hash(dataset) != manifest['source_dataset_sha256']
                or file_hash(experiment_path) != manifest['source_experiment_sha256']):
            raise DatasetError('evaluator or source inputs changed during collection')
        manifest['status'] = 'complete'
    except (Exception, KeyboardInterrupt) as exc:
        manifest['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        manifest['collection_finished_at'] = utc_now_iso()
        manifest['gpu_after'] = gpu_snapshot()
        manifest['artifact_sha256'] = {name: file_hash(output / name) for name in ARTIFACTS}
        write_json(output / 'manifest.json', manifest)
    return manifest


def _load(directory: Path):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('status') != 'complete' or manifest.get('protocol') != PROTOCOL:
        raise DatasetError('incomplete or unsupported model-only pass')
    hashes = manifest.get('artifact_sha256', {})
    if set(hashes) != set(ARTIFACTS) or any(file_hash(directory / name) != digest for name, digest in hashes.items()):
        raise DatasetError('model-only artifacts changed after collection')
    if any(manifest[f'{name}_sha256'] != hashes[f'{name}.jsonl' if name == 'dataset' else f'{name}.json']
           for name in ('dataset', 'experiment')):
        raise DatasetError('inconsistent artifact hashes')
    rows = read_dataset(directory / 'dataset.jsonl')
    _questions(rows)
    experiment = read_experiment(directory / 'experiment.json')
    samples = [json.loads(s) for s in (directory / 'predictions.jsonl').read_text().splitlines()]
    expected = {(r['trace_id'], i) for r in rows for i in range(experiment.repetitions)}
    if (manifest['rows'] != len(rows) or len(samples) != len(expected)
            or {(s['trace_id'], s['repetition']) for s in samples} != expected
            or any(s['backend'] != manifest['backend'] for s in samples)):
        raise DatasetError('model-only samples do not join the frozen cases exactly')
    for sample in samples:
        validate_answers(sample['answers'], rows[0]['questions'])
        expected_condition = 'first_observed' if sample['repetition'] == 0 else 'repeated_request'
        if sample['condition'] != expected_condition:
            raise DatasetError('invalid timing condition')
    return manifest, rows, samples


def combine_model_passes(runs: list[Path], output: Path) -> dict:
    if output.exists():
        raise DatasetError('report output already exists')
    if not runs:
        raise DatasetError('model-only passes are required')
    loaded = [_load(path) for path in runs]
    first = loaded[0][0]
    names = [m['backend'] for m, _, _ in loaded]
    if len(set(names)) != len(names) or set(names) != set(first['required_backends']):
        raise DatasetError('need exactly one complete pass per configured backend')
    for manifest, _, _ in loaded:
        if any(manifest[key] != first[key] for key in (
                'dataset_sha256', 'experiment_sha256', 'evaluator_sha256', 'required_backends')):
            raise DatasetError('model-only passes use incompatible inputs or evaluator code')
    intervals = sorted((m['collection_started_at'], m['collection_finished_at']) for m, _, _ in loaded)
    if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:])):
        raise DatasetError('model-only collection passes overlap')
    report = {
        'comparison_kind': 'model_only', 'purpose': 'benchmark', 'mode': 'labeled',
        'rows': first['rows'], 'dataset_sha256': first['dataset_sha256'],
        'models': {}, 'latency': {}, 'audit': {}, 'runtime': {},
        'selection': {'status': 'inconclusive', 'reason': 'Exploratory model-only comparison; no independent model-selection claim.'},
        'notes': [
            'Only model answers are measured. No historical rules, policy or final system decisions are replayed.',
            'Quality uses repetition zero. Repeated passes contribute timing and answer-stability evidence only.',
            'Handling interventions mean a predicted handling other than allow, compared with question labels.',
            'HTTP time excludes model loading, reviewer calls and human waiting. Cache and cold-start claims are not made.',
        ],
    }
    for manifest, rows, samples in loaded:
        name = manifest['backend']
        predictions = {s['trace_id']: s['answers'] for s in samples if s['repetition'] == 0}
        report['models'][name] = detailed_metrics([predictions[r['trace_id']] for r in rows], rows)
        report['latency'][name] = {}
        for key, field in (('http', 'client_latency_ms'), ('server', 'server_latency_ms')):
            summary = latency_summary(samples, field)
            report['latency'][name][key] = {'first_pass': summary['first_observed'], 'repeated_pass': summary['repeated_request']}
        report['latency'][name]['changed_repeat_answers'] = sum(
            s['answers'] != predictions[s['trace_id']] for s in samples if s['repetition'] > 0)
        report['audit'][name] = manifest['audit']
        report['runtime'][name] = {
            'before': manifest['identity_before'], 'after': manifest['identity_after'],
            'hardware': manifest['declared_hardware'], 'timing': manifest['timing'],
            'gpu_before': manifest['gpu_before'], 'gpu_after': manifest['gpu_after'],
        }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'report.json', report)
    lines = [
        '# Model-only comparison', '', f'Cases: {report["rows"]}. Selection: inconclusive.', '',
        str(first['declared_hardware'].get('dataset_note', 'Exploratory comparison.')), '',
        *[f'- {note}' for note in report['notes']], '',
        '| Backend | Handling misses | Unnecessary handling interventions | HTTP p50 ms (first pass) |',
        '|---|---:|---:|---:|',
    ]
    for name in names:
        handling = report['models'][name]['handling']['intervention']
        latency = report['latency'][name]['http']['first_pass']['p50_ms']
        lines.append(f'| {name} | {handling["missed"]}/{handling["needed"]} | '
                     f'{handling["unnecessary"]}/{handling["safe"]} | {latency:.1f} |')
    lines += ['', '| Backend / question / class | Correct | Support |', '|---|---:|---:|']
    for name in names:
        for question, metrics in report['models'][name].items():
            for label, counts in metrics['classes'].items():
                lines.append(f'| {name} / {question} / {label} | {counts["correct"]} | {counts["support"]} |')
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
    write_json(output / 'manifest.json', {'status': 'complete', 'protocol': PROTOCOL,
               'runs': [str(p.resolve()) for p in runs], 'report_sha256': file_hash(output / 'report.json')})
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--experiment', type=Path)
    parser.add_argument('--backend', choices=('laya_current', 'laya_released', 'kev'))
    parser.add_argument('--runs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.runs:
        if args.dataset or args.experiment or args.backend:
            parser.error('--runs cannot be combined with collection arguments')
        combine_model_passes(args.runs, args.output)
    else:
        if not (args.dataset and args.experiment and args.backend):
            parser.error('collection requires --dataset, --experiment and --backend')
        collect_model_pass(args.dataset, args.experiment, args.backend, args.output)


if __name__ == '__main__':
    main()
