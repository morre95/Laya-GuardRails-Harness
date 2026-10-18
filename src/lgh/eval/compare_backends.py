"""Sequential backend collection and strict joins of frozen comparison passes."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
import sys

from lgh.eval.backend_contract import Experiment, digest, read_inputs, validate_answers
from lgh.eval.backend_replay import replay_assessment
from lgh.eval.backend_setup import gpu_snapshot
from lgh.eval.backends import HttpBackend
from lgh.eval.compare import audit_dataset, file_hash, state_hash
from lgh.ids import utc_now_iso
from lgh.train.data import DatasetError

PROTOCOL_VERSION = 1
ARTIFACTS = ('dataset.jsonl', 'replay.jsonl', 'experiment.json', 'predictions.jsonl', 'decisions.jsonl')


def evaluator_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    return digest({'sources': {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob('*.py'))},
                   'python': sys.version, 'pydantic': version('pydantic'), 'pyyaml': version('pyyaml')})


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows))


def read_experiment(path: Path) -> Experiment:
    data = json.loads(path.read_text())
    for spec in data.get('backends', {}).values():
        if spec.get('training_dataset'):
            spec['training_dataset'] = str((path.parent / spec['training_dataset']).resolve())
    return Experiment.model_validate(data)


def audit_backend(rows: list[dict], spec) -> dict:
    metadata = {}
    model_dir = Path(spec.model)
    config_path = model_dir / 'rl_agent_config.json'
    if config_path.is_file():
        metadata = json.loads(config_path.read_text()).get('lgh_training', {})
        if (spec.training_dataset_sha256 and metadata.get('dataset_sha256')
                and spec.training_dataset_sha256 != metadata['dataset_sha256']):
            raise DatasetError('declared training hash does not match checkpoint metadata')
    # Only checkpoint metadata establishes which training export belongs to a
    # local model. An arbitrary user-supplied hash is not that evidence.
    training = Path(spec.training_dataset) if spec.training_dataset else None
    audit = audit_dataset(rows, training, metadata)
    audit['provenance'] = spec.provenance
    audit['declared_training_sha256'] = spec.training_dataset_sha256
    if spec.provenance == 'local_finetuned' and not metadata.get('dataset_sha256'):
        audit['status'] = 'unverified_local_checkpoint'
    audit['local_weights_sha256'] = None
    weights = model_dir / 'model.safetensors'
    if weights.is_file():
        audit['local_weights_sha256'] = file_hash(weights)
        if spec.revision and spec.revision != audit['local_weights_sha256']:
            raise DatasetError('declared local revision does not match model.safetensors SHA-256')
    audit['local_config_sha256'] = file_hash(config_path) if config_path.is_file() else None
    audit['notes'] = 'Exact ID/state audit only; earlier fine-tunes, near-duplicates and released training history may be unknown.'
    return audit


def collect_backend(dataset: Path, replay: Path, experiment_path: Path, backend: str, output: Path,
                    *, labels: Path | None = None, unlabeled: bool = False,
                    allow_overlap: bool = False, timeout: float = 30) -> dict:
    if output.exists():
        raise DatasetError(f'{output} already exists; choose a new output directory')
    experiment = read_experiment(experiment_path)
    if backend not in experiment.backend_names():
        raise DatasetError('unknown or deduplicated backend name')
    if not math.isfinite(timeout) or timeout <= 0:
        raise DatasetError('timeout must be finite and positive')
    rows, cases = read_inputs(dataset, replay, experiment, labels=labels, unlabeled=unlabeled)
    spec = experiment.backends[backend]
    audit = audit_backend(rows, spec)
    unresolved_revision = not spec.revision or spec.revision in ('main', 'latest', 'v1.0', 'unknown')
    if not allow_overlap and (audit['status'] != 'no_exact_overlap' or unresolved_revision or not spec.code_revision):
        raise DatasetError('data/model audit is unverified; --allow-overlap explicitly permits exploratory evidence')
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output/'dataset.jsonl', rows)
    write_rows(output/'replay.jsonl', [c.model_dump(mode='json') for c in cases])
    write_json(output/'experiment.json', experiment.model_dump(mode='json'))
    write_rows(output/'predictions.jsonl', [])
    write_rows(output/'decisions.jsonl', [])
    manifest = {
        'protocol_version': PROTOCOL_VERSION, 'status': 'incomplete', 'created_at': utc_now_iso(),
        'evaluator_sha256': evaluator_fingerprint(),
        'backend': backend, 'required_backends': experiment.backend_names(), 'rows': len(rows),
        'purpose': experiment.purpose,
        'mode': 'unlabeled' if unlabeled else 'labeled', 'exploratory': allow_overlap,
        'source_dataset_sha256': file_hash(dataset), 'source_replay_sha256': file_hash(replay),
        'labels_sha256': file_hash(labels) if labels else None,
        'dataset_sha256': file_hash(output/'dataset.jsonl'),
        'replay_sha256': file_hash(output/'replay.jsonl'),
        'experiment_sha256': file_hash(output/'experiment.json'),
        'audit': audit, 'declared_hardware': experiment.hardware,
        'gpu_before': gpu_snapshot(),
        'timing': {'warmup': experiment.warmup, 'repetitions': experiment.repetitions,
                   'order': 'dataset order within each repetition', 'concurrency': 1,
                   'schedule': 'one backend per separately collected pass',
                   'cache_protocol': 'first observed vs repeated request; not a claim of cache misses',
                   'harness_timing': 'HTTP plus isolated replay for PASS; replay only for hard-rule bypass',
                   'true_peak_vram': None},
        'replay': {'mode': 'enforce', 'snapshot_mode': experiment.config.mode.value,
                   'reviewer': 'unavailable', 'session_policy': 'reset from each case snapshot per sample',
                   'rules': 'frozen capture results; no live filesystem evaluation'},
    }
    write_json(output/'manifest.json', manifest)
    try:
        manifest['collection_started_at'] = utc_now_iso()
        client = HttpBackend(spec, timeout=timeout)
        manifest['identity_before'] = client.identity()
        # Disjoint, excluded warmup. Never mutate a scored state or consume its
        # labels; appended synthetic context only affects this discarded request.
        warmup_state = deepcopy(rows[0]['state'])
        states = {state_hash(r) for r in rows}
        suffix = 0
        while True:
            warmup_state['goal'] = rows[0]['state']['goal'] + f' [LGH excluded warmup {suffix}]'
            if state_hash({'state': warmup_state}) not in states:
                break
            suffix += 1
        for _ in range(experiment.warmup):
            client.predict(warmup_state, rows[0]['questions'])
        seen_states = set()
        for repetition in range(experiment.repetitions):
            for row, case in zip(rows, cases, strict=True):
                prediction = client.predict(row['state'], row['questions'])
                validate_answers(prediction['answers'], row['questions'])
                result = replay_assessment(row, case, experiment, backend, prediction['answers'])
                h = state_hash(row)
                condition = 'repeated_request' if h in seen_states else 'first_observed'
                seen_states.add(h)
                sample = {'trace_id': row['trace_id'], 'backend': backend,
                          'repetition': repetition, 'condition': condition, **prediction}
                result.update(repetition=repetition, condition=condition,
                              accounted_harness_ms=result['replay_latency_ms'] + (
                                  prediction['client_latency_ms'] if result['model_dependent'] else 0))
                with (output/'predictions.jsonl').open('a') as stream:
                    stream.write(json.dumps(sample, allow_nan=False) + '\n')
                with (output/'decisions.jsonl').open('a') as stream:
                    stream.write(json.dumps(result, allow_nan=False) + '\n')
        manifest['identity_after'] = client.identity()
        before, after = manifest['identity_before']['observed'], manifest['identity_after']['observed']
        for key in ('model', 'run', 'base', 'device', 'dtype', 'backend', 'temperature', 'truncate_states'):
            if before.get(key) != after.get(key):
                raise DatasetError(f'backend identity/config changed during collection: {key}')
        if evaluator_fingerprint() != manifest['evaluator_sha256']:
            raise DatasetError('evaluator code changed during collection')
        manifest['status'] = 'complete'
        manifest['sample_count'] = len(rows) * experiment.repetitions
    except Exception as exc:
        manifest['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        manifest['collection_finished_at'] = utc_now_iso()
        manifest['gpu_after'] = gpu_snapshot()
        manifest['artifact_sha256'] = {name: file_hash(output/name) for name in ARTIFACTS}
        write_json(output/'manifest.json', manifest)
    return manifest


def _load_pass(directory: Path) -> tuple[dict, list[dict], list[dict], list[dict], list]:
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest.get('status') != 'complete' or manifest.get('protocol_version') != PROTOCOL_VERSION:
        raise DatasetError(f'{directory}: incomplete or unsupported collection pass')
    hashes = manifest.get('artifact_sha256', {})
    if set(hashes) != set(ARTIFACTS) or any(file_hash(directory/name) != h for name, h in hashes.items()):
        raise DatasetError(f'{directory}: frozen artifacts changed after collection')
    for field, name in [('dataset_sha256','dataset.jsonl'), ('replay_sha256','replay.jsonl'),
                        ('experiment_sha256','experiment.json')]:
        if manifest[field] != hashes[name]:
            raise DatasetError(f'{directory}: inconsistent manifest hashes')
    experiment = read_experiment(directory/'experiment.json')
    rows, cases = read_inputs(directory/'dataset.jsonl', directory/'replay.jsonl', experiment,
                              unlabeled=manifest['mode'] == 'unlabeled')
    predictions, decisions = [
        [json.loads(line) for line in (directory/name).read_text().splitlines() if line.strip()]
        for name in ('predictions.jsonl', 'decisions.jsonl')]
    expected = {(r['trace_id'], i) for r in rows for i in range(experiment.repetitions)}
    for samples in (predictions, decisions):
        keys = {(s['trace_id'], s['repetition']) for s in samples}
        if len(keys) != len(samples) or keys != expected or any(s['backend'] != manifest['backend'] for s in samples):
            raise DatasetError(f'{directory}: samples do not join the frozen cases exactly')
    for sample in predictions:
        validate_answers(sample['answers'], rows[0]['questions'])
    return manifest, rows, predictions, decisions, cases


def combine_runs(runs: list[Path], output: Path) -> dict:
    if output.exists():
        raise DatasetError(f'{output} already exists; choose a new output directory')
    if not runs:
        raise DatasetError('at least the primary backend passes are required')
    loaded = [_load_pass(Path(p)) for p in runs]
    first = loaded[0][0]
    names = [v[0]['backend'] for v in loaded]
    if len(set(names)) != len(names) or set(names) != set(first['required_backends']):
        raise DatasetError('need one complete pass for every distinct configured backend')
    for manifest, *_ in loaded:
        for key in ('dataset_sha256', 'replay_sha256', 'experiment_sha256', 'evaluator_sha256', 'purpose', 'mode', 'required_backends'):
            if manifest[key] != first[key]:
                raise DatasetError(f'collection passes have incompatible {key}')
    if first.get('evaluator_sha256') != evaluator_fingerprint():
        raise DatasetError('report evaluator differs from the collection evaluator')
    intervals = []
    for manifest, *_ in loaded:
        try:
            start = datetime.fromisoformat(manifest['collection_started_at'].replace('Z', '+00:00'))
            finish = datetime.fromisoformat(manifest['collection_finished_at'].replace('Z', '+00:00'))
            if start.tzinfo is None or finish.tzinfo is None or finish < start:
                raise ValueError('invalid interval')
        except (ValueError, KeyError) as exc:
            raise DatasetError('collection timing interval is invalid or missing') from exc
        intervals.append((start, finish))
    intervals.sort()
    if any(intervals[i][0] < intervals[i-1][1] for i in range(1, len(intervals))):
        raise DatasetError('collection passes overlap; sequential timing protocol violated')
    from lgh.eval.backend_report import build_report, render_report
    report, disagreements = build_report(loaded)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('dataset.jsonl', 'replay.jsonl', 'experiment.json'):
        (output/name).write_bytes((Path(runs[0])/name).read_bytes())
    write_rows(output/'predictions.jsonl', [s for _, _, p, _, _ in loaded for s in p])
    write_rows(output/'decisions.jsonl', [s for _, _, _, d, _ in loaded for s in d])
    write_rows(output/'disagreements.jsonl', disagreements)
    report['collection_passes'] = [str(Path(p).resolve()) for p in runs]
    write_json(output/'report.json', report)
    (output/'report.md').write_text(render_report(report))
    write_json(output/'manifest.json', {'protocol_version': PROTOCOL_VERSION, 'status': 'complete',
                                      'kind': 'combined_report', 'passes': [v[0] for v in loaded]})
    return report
