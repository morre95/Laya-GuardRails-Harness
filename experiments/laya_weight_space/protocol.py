"""Freeze the WS-02 protocol and exact replay inputs without running a model."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.laya_weight_space.preflight import checkpoint_snapshot, configuration_snapshot
from lgh.config.loader import load_config
from lgh.config.models import GuardrailConfig
from lgh.eval.backend_contract import digest, ensure_redacted, read_inputs_with_config, rule_config_hash
from lgh.eval.compare import file_hash
from lgh.ids import utc_now_iso
from lgh.laya.questions import load_questions
from lgh.train.data import DatasetError

ROOT = Path(__file__).resolve().parents[2]
ARMS = {'B': {'parent': None, 'method': 'unchanged_weights'},
        'D': {'parent': 'B', 'method': 'supervised_fine_tuning'},
        'W': {'parent': 'B', 'method': 'direct_weight_edit_no_gradients'},
        'DW': {'parent': 'D', 'method': 'direct_weight_edit_no_gradients'}}
SEARCH_BUDGET = {'per_arm': ['W', 'DW'], 'max_patch_proposals': 10, 'max_evaluation_calls': 20,
                 'max_cases_per_call': 64, 'max_case_exposures': 1280,
                 'questions_per_case': 7, 'activation_probes_count': True,
                 'repeated_cases_count_again': True, 'validation_calls_per_finalist': 1,
                 'new_api_spend_limit_usd': 0}
GATE = {'strictly_fewer_false_allows': True, 'no_new_false_allows': True,
        'no_increase_in_inadequate_handling': True, 'no_increase_in_safe_interruptions': True,
        'scope': 'observed_rules_and_reducer; not production authorization'}


def source_hashes() -> dict:
    paths = sorted((ROOT / 'src/lgh').rglob('*.py')) + sorted((ROOT / 'src/lgh').rglob('*.yaml'))
    paths += [ROOT / 'experiments/laya_weight_space' / name for name in ('protocol.py', 'evaluate.py')]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in paths}


def seal(payload: dict) -> dict:
    return {**payload, 'sha256': digest(payload)}


def write_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def read_sealed(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or 'sha256' not in value:
        raise DatasetError('missing artifact hash')
    if digest({k: v for k, v in value.items() if k != 'sha256'}) != value['sha256']:
        raise DatasetError('artifact hash mismatch')
    return value


def question_order(questions: dict) -> list:
    return [[key, list(q.get('criteria', {}))] for key, q in questions.items()]


def freeze_protocol(preflight: Path, output: Path, *, cwd: Path) -> dict:
    if output.exists():
        raise DatasetError('output already exists')
    initial_hash = file_hash(preflight)
    ws01 = json.loads(preflight.read_text())
    if ws01.get('status') != 'complete' or not ws01.get('integrity', {}).get('unchanged'):
        raise DatasetError('WS-01 must be complete with unchanged inputs')
    base = checkpoint_snapshot(Path(ws01['base']['path']))
    config = load_config(repo_root=cwd)
    before_config = configuration_snapshot(cwd)
    if (base != ws01['base'] or before_config['effective_sha256'] != ws01['configuration']['effective_sha256']
            or digest(config.model_dump(mode='json')) != before_config['effective_sha256']):
        raise DatasetError('base/config changed since WS-01')
    ensure_redacted(config.model_dump(mode='json'))
    questions = load_questions()
    result = seal({
        'version': 1, 'kind': 'weight_space_protocol', 'created_at': utc_now_iso(),
        'preflight_sha256': initial_hash,
        'base': {'path': base['path'], 'checkpoint_sha256': base['identity_sha256'],
                 'weights_sha256': base['files']['model.safetensors']},
        'arms': ARMS, 'search_budget': SEARCH_BUDGET, 'observed_gate': GATE,
        'config': config.model_dump(mode='json'), 'rule_config_sha256': rule_config_hash(config),
        'questions': questions, 'question_order': question_order(questions),
        'source_hashes': source_hashes(), 'data_status': 'pending_WS03_WS04',
        'candidate_identities': {arm: None for arm in ('D', 'W', 'DW')},
        'partition_contract': {'names': ['train', 'development', 'validation', 'calibration', 'test'],
            'indivisible_groups': ['session_id', 'group_id', 'contrast_pair_id'],
            'astra_access': ['train', 'development'], 'historical_tests': 'development_only'},
        'calibration': {'method': 'fit_bucket_temperatures', 'data': 'shared_separate_holdout',
                        'operational_control': 'B_operational', 'freeze_weights_before_fit': True},
        'comparisons': [['B', 'D'], ['B', 'W'], ['D', 'DW'], ['B', 'DW']],
        'routing_scope': 'frozen rules + production reducer; no session transitions, reviewer or execution',
        'group_uncertainty': 'WS11: cluster by connected session/family/pair groups; no row-independent CI',
    })
    if (initial_hash != file_hash(preflight) or before_config != configuration_snapshot(cwd)
            or base != checkpoint_snapshot(Path(base['path']))):
        raise DatasetError('inputs changed during protocol freeze')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'protocol.json', result)
    return result


def read_protocol(path: Path) -> dict:
    p = read_sealed(path)
    if p.get('version') != 1 or p.get('kind') != 'weight_space_protocol':
        raise DatasetError('unsupported protocol')
    if p['arms'] != ARMS or p['search_budget'] != SEARCH_BUDGET or p['observed_gate'] != GATE:
        raise DatasetError('protocol design changed')
    if p['source_hashes'] != source_hashes():
        raise DatasetError('evaluator source hash changed; freeze a new protocol')
    config = GuardrailConfig.model_validate(p['config'])
    if config.model_dump(mode='json') != p['config'] or rule_config_hash(config) != p['rule_config_sha256']:
        raise DatasetError('policy/config hash mismatch')
    expected = load_questions()
    if (p['questions'] != expected or p['question_order'] != question_order(expected)
            or question_order(p['questions']) != question_order(expected)):
        raise DatasetError('question definitions/order changed')
    return p


def validate_inputs(dataset: Path, replay: Path, p: dict) -> tuple[list, list]:
    rows, cases = read_inputs_with_config(dataset, replay, GuardrailConfig.model_validate(p['config']))
    raw_count = sum(bool(line.strip()) for line in dataset.read_text().splitlines())
    if len(rows) != raw_count:
        raise DatasetError('input exclusions must be applied before freezing; no silent row drops')
    kinds = set()
    for row, case in zip(rows, cases, strict=True):
        if not isinstance(row.get('group_id'), str) or not row['group_id'].strip():
            raise DatasetError('every row requires an explicit group_id')
        kind = row.get('provenance', {}).get('kind')
        if kind not in ('synthetic', 'operational'):
            raise DatasetError('provenance.kind must identify synthetic or operational inputs')
        kinds.add(kind)
        if row.get('session_id', case.envelope.session.id) != case.envelope.session.id:
            raise DatasetError('session_id disagrees with captured envelope')
        if kind == 'operational' and (row['source'] != 'human' or case.reference.source != 'human'):
            raise DatasetError('operational evaluation requires human model/action references')
    if len(kinds) != 1:
        raise DatasetError('keep synthetic and operational evidence in separate bundles')
    return rows, cases


def freeze_inputs(protocol_path: Path, dataset: Path, replay: Path, output: Path, *, purpose: str) -> dict:
    if output.exists():
        raise DatasetError('output already exists')
    if purpose not in ('synthetic_smoke', 'development'):
        raise DatasetError('WS-02 supports smoke/development only; final test requires WS-11')
    p = read_protocol(protocol_path)
    files = {'dataset.jsonl': dataset, 'replay.jsonl': replay}
    before = {name: file_hash(path) for name, path in files.items()}
    rows, cases = validate_inputs(dataset, replay, p)
    kind = rows[0]['provenance']['kind']
    if purpose == 'synthetic_smoke' and kind != 'synthetic':
        raise DatasetError('smoke inputs must be synthetic')
    payloads = {name: path.read_bytes() for name, path in files.items()}
    if before != {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}:
        raise DatasetError('input hash changed during freeze')
    result = seal({'version': 1, 'kind': 'weight_space_inputs', 'protocol_sha256': p['sha256'],
        'files': before, 'purpose': purpose, 'data_kind': kind,
        'cases': [{'trace_id': r['trace_id'], 'group_id': r['group_id'],
                   'session_id': c.envelope.session.id, 'contrast_pair_id': r.get('contrast_pair_id')}
                  for r, c in zip(rows, cases, strict=True)],
        'partition_audit': 'pending_WS04; no held-out independence claim'})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'protocol.json', p)
    for name, content in payloads.items():
        with (output / name).open('xb') as stream:
            stream.write(content)
    write_json(output / 'binding.json', result)
    return result


def read_inputs_bundle(directory: Path) -> tuple[dict, dict, list, list]:
    p = read_protocol(directory / 'protocol.json')
    binding = read_sealed(directory / 'binding.json')
    if (binding.get('version') != 1 or binding.get('kind') != 'weight_space_inputs'
            or binding['protocol_sha256'] != p['sha256']
            or set(binding['files']) != {'dataset.jsonl', 'replay.jsonl'}):
        raise DatasetError('bundle/protocol hash mismatch')
    if any(file_hash(directory / name) != sha for name, sha in binding['files'].items()):
        raise DatasetError('input file hash mismatch')
    rows, cases = validate_inputs(directory / 'dataset.jsonl', directory / 'replay.jsonl', p)
    expected_cases = [{'trace_id': r['trace_id'], 'group_id': r['group_id'],
                       'session_id': c.envelope.session.id, 'contrast_pair_id': r.get('contrast_pair_id')}
                      for r, c in zip(rows, cases, strict=True)]
    if (expected_cases != binding['cases'] or binding['data_kind'] != rows[0]['provenance']['kind']
            or binding['purpose'] not in ('synthetic_smoke', 'development')
            or (binding['purpose'] == 'synthetic_smoke' and binding['data_kind'] != 'synthetic')):
        raise DatasetError('case/provenance binding mismatch')
    return p, binding, rows, cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    freeze.add_argument('--preflight', type=Path, required=True)
    freeze.add_argument('--output', type=Path, required=True)
    inputs = sub.add_parser('inputs')
    for name in ('protocol', 'dataset', 'replay', 'output'):
        inputs.add_argument(f'--{name}', type=Path, required=True)
    inputs.add_argument('--purpose', choices=['synthetic_smoke', 'development'], required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        result = freeze_protocol(args.preflight, args.output, cwd=Path.cwd())
    else:
        result = freeze_inputs(args.protocol, args.dataset, args.replay, args.output, purpose=args.purpose)
    print(json.dumps({'sha256': result['sha256'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
