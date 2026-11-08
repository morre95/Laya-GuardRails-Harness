"""WS-04 group boundaries and history audit; never executes dataset actions."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import re

from lgh.eval.backend_contract import digest
from lgh.train.data import DatasetError

GOALS = dict(train=30, development=15, validation=15, calibration=15)
GROUP_KEYS = ('group_id', 'session_id', 'contrast_pair_id', 'semantic_group')

# Conservative author review: these related mechanisms must stay together.
SEMANTIC_LINKS = [
    ['archive-extraction-collision', 'restore-archive-scope'],
    ['backup-integrity', 'backup-freshness'],
    ['review-current-versus-stale', 'atomic-rename-stale-version'],
    ['hardlink-versus-independent-copy', 'backup-hardlink-alias'],
    ['symlink-write-boundary', 'symlink-replacement-versus-follow'],
    ['encoding-loss', 'line-ending-signatures'],
    ['firewall-rule-order', 'role-sync-default-deny'],
]
HISTORY = {
    'comparisons/20261017-prepared/original-training-export.jsonl': 'inherited_base_training',
    'comparisons/20261017-prepared/unseen.jsonl': 'historical_evaluation',
    'comparisons/laya-v2/data/train.jsonl': 'historical_candidate_training',
    'comparisons/laya-v2/data/validation.jsonl': 'historical_validation',
    'comparisons/laya-v2/data/calibration.jsonl': 'historical_calibration',
    'comparisons/laya-v2/data-02/train.jsonl': 'historical_candidate_training',
    'comparisons/laya-v2/data-02/validation.jsonl': 'historical_validation',
    'comparisons/laya-v2/data-02/calibration.jsonl': 'historical_calibration',
    'comparisons/laya-v2/challenge.jsonl': 'historical_test_now_development',
    'comparisons/laya-v2/confirmation.jsonl': 'historical_test_now_development',
}


def identities(row: dict) -> set[tuple[str, str]]:
    result = {(key, row[key]) for key in ('trace_id', *GROUP_KEYS) if row.get(key)}
    if row.get('state'):
        result.add(('state', digest(row['state'])))
    return result


def connected_groups(rows: list[dict]) -> list[list[dict]]:
    """Transitive closure, including exact state and explicitly reviewed semantic links."""
    parents = list(range(len(rows)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen = {}
    for i, row in enumerate(rows):
        for identity in identities(row):
            if identity in seen:
                parents[root(i)] = root(seen[identity])
            else:
                seen[identity] = i
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    return sorted((sorted(g, key=lambda r: r['trace_id']) for g in groups.values()),
                  key=lambda g: g[0]['trace_id'])


def audit_splits(partitions: dict[str, list[dict]], history: list[dict]) -> dict:
    owners = {}
    historical = set().union(*(identities(r) for r in history)) if history else set()
    for name, rows in partitions.items():
        if not rows:
            raise DatasetError(f'{name}: empty partition')
        traces = set()
        for row in rows:
            if row['trace_id'] in traces:
                raise DatasetError('trace overlap within partition')
            traces.add(row['trace_id'])
            for identity in identities(row):
                previous = owners.setdefault(identity, name)
                if previous != name:
                    raise DatasetError(f'{identity[0]} overlap: {previous}/{name}')
                if identity in historical:
                    raise DatasetError(f'{identity[0]} overlap with history: {row["trace_id"]}')
    return {'exact_overlap': 0, 'history_rows': len(history),
            'checked': ['trace_id', 'state', *GROUP_KEYS], 'unknown_pretraining': 'unknown'}


def split_groups(rows: list[dict], *, goals=None, development_only=None) -> dict[str, list[dict]]:
    goals = GOALS if goals is None else goals
    development_only = development_only or set()
    groups = connected_groups(rows)
    if len(groups) < sum(goals.values()):
        raise DatasetError(f'need {sum(goals.values())} connected groups; have {len(groups)}')
    result = {name: [] for name in goals}
    counts = Counter()
    support = {name: Counter() for name in goals}

    def classes(group):
        return Counter((k, str(v)) for row in group for k, v in row['labels'].items())

    def add(name, group):
        result[name].extend(deepcopy(group))
        counts[name] += 1
        support[name].update(classes(group))

    remaining = []
    for group in groups:
        if any(r['group_id'] in development_only for r in group):
            add('development', group)
        else:
            remaining.append(group)
    required = sum(max(0, n-counts[name]) for name, n in goals.items())
    if len(remaining) < required:
        raise DatasetError('development-only groups leave too few groups for the other partitions')
    total = classes(rows)
    # Place scarce labels first, then favor partitions missing those labels.
    remaining.sort(key=lambda g: (-sum(1/total[c] for c in classes(g)), g[0]['trace_id']))
    for group in remaining:
        candidates = [name for name in goals if counts[name] < goals[name]] or ['train']
        name = max(candidates, key=lambda n: (
            sum(1/(total[c]*(1+support[n][c]/goals[n])) for c in classes(group)),
            (goals[n]-counts[n])/goals[n], -list(goals).index(n)))
        add(name, group)
    for name, members in result.items():
        members.sort(key=lambda r: r['trace_id'])
        for row in members:
            row.setdefault('provenance', {})['partition'] = name
    return result


def review_links(rows: list[dict]) -> list[dict]:
    rows = deepcopy(rows)
    mapping = {family: f'reviewed-link-{i}' for i, group in enumerate(SEMANTIC_LINKS) for family in group}
    for row in rows:
        row['semantic_group'] = mapping.get(row['group_id'], row['group_id'])
    return rows


def near_matches(rows: list[dict], history: list[dict], threshold=0.65) -> list[dict]:
    """Lexical screen, not a proof of semantic independence. No label comparison."""
    stop = set('the a an and or of to in with only it is its this that all no has have be as for local public'.split())

    def tokens(row):
        return set(re.findall(r'[a-z]+', row['state'].get('goal', '').lower())) - stop

    result = []
    reference = [(r, tokens(r)) for r in history]
    for i, row in enumerate(rows):
        left = tokens(row)
        for other, right in reference + [(r, tokens(r)) for r in rows[:i]
                                         if r['semantic_group'] != row['semantic_group']]:
            if not left or not right:
                continue
            similarity = len(left & right) / len(left | right)
            if similarity >= threshold:
                result.append({'trace_id': row['trace_id'], 'group_id': row['group_id'],
                    'other_trace_id': other['trace_id'], 'other_group_id': other.get('group_id'),
                    'historical_path': other.get('_history_path'), 'goal_jaccard': round(similarity, 6)})
    return result


def read_history(root: Path) -> tuple[list[dict], list[dict]]:
    from lgh.eval.compare import file_hash
    rows, manifest = [], []
    for name, role in HISTORY.items():
        path = root / name
        before = file_hash(path)
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for row in records:
            if not isinstance(row.get('trace_id'), str) or not isinstance(row.get('state'), dict):
                raise DatasetError(f'historical identity missing: {name}')
            # Legacy labels can be invalid. They are neither copied nor targets here.
            rows.append({k: row[k] for k in ('trace_id', 'state', *GROUP_KEYS) if k in row}
                        | {'_history_path': name})
        if file_hash(path) != before:
            raise DatasetError('history changed during read')
        manifest.append({'path': name, 'role': role, 'sha256': before, 'rows': len(records),
                         'missing_session_ids': sum(not r.get('session_id') for r in records)})
    return rows, manifest


def access_probe(paths: list[Path]) -> dict:
    readable = {}
    for path in paths:
        try:
            with path.open('rb') as stream:
                stream.read(1)
            readable[str(path)] = True
        except PermissionError:
            readable[str(path)] = False
    # A denied file alone cannot attest that an agent cannot read another copy
    # or change permissions as the same user. No positive isolation claim here.
    return {'uid': os.geteuid(), 'readable': readable, 'isolated': False,
            'scope': 'current agent process; source curriculum and pool also exposed',
            'reason': 'user confirms no environment outside Astra read access'}


def freeze_pool(protocol_path: Path, pool: Path, output: Path, *, root: Path, goals=None) -> dict:
    from lgh.config.models import GuardrailConfig
    from lgh.eval.compare import file_hash
    from lgh.rules.engine import evaluate_rules
    from lgh.schema.envelope import ActionEnvelope
    from lgh.train.data import class_support, load_rows, support_warnings
    from experiments.laya_weight_space.protocol import read_protocol, seal, validate_inputs, write_json
    if output.exists():
        raise DatasetError('output already exists')
    p = read_protocol(protocol_path)
    pool_manifest_hash = file_hash(pool / 'manifest.json')
    manifest = json.loads((pool / 'manifest.json').read_text())
    required = {'pool.jsonl', 'envelopes.jsonl', 'model-inputs.jsonl', 'excluded.jsonl', 'review.md'}
    if set(manifest.get('files', {})) != required:
        raise DatasetError('pool manifest has incomplete files')
    if any(file_hash(pool / name) != sha for name, sha in manifest['files'].items()):
        raise DatasetError('pool file hash mismatch')
    if manifest['metadata']['protocol_sha256'] != p['sha256']:
        raise DatasetError('pool protocol mismatch')
    for path, sha in manifest['metadata']['source_hashes'].items():
        if file_hash(Path(path)) != sha:
            raise DatasetError('pool source hash changed; rebuild into a new directory')
    rows = review_links(load_rows(pool / 'pool.jsonl'))
    if any(r.get('source') != 'frontier' or r.get('provenance', {}).get('kind') != 'synthetic' for r in rows):
        raise DatasetError('this pool builder requires explicitly frontier synthetic data')
    history, history_manifest = read_history(root)
    audit_splits({'pool': rows}, history)
    similar = near_matches(rows, history)
    # Unresolved new/new neighbors require an explicit group review before freeze.
    if any(not item['historical_path'] for item in similar):
        raise DatasetError('near duplicate pool groups require explicit semantic links')
    development_only = {item['group_id'] for item in similar}
    splits = split_groups(rows, goals=goals, development_only=development_only)
    audit = audit_splits(splits, history)
    envelopes = [json.loads(line) for line in (pool / 'envelopes.jsonl').read_text().splitlines() if line.strip()]
    by_id = {r['trace_id']: r for r in envelopes}
    if len(by_id) != len(envelopes) or set(by_id) != {r['trace_id'] for r in rows}:
        raise DatasetError('envelopes must join pool exactly once')
    config = GuardrailConfig.model_validate(p['config'])
    sides = {}
    for trace_id, record in by_id.items():
        envelope = ActionEnvelope.model_validate(record['envelope'])
        if envelope.repo.root != '/workspace/ws03' or envelope.repo.cwd != '/workspace/ws03':
            raise DatasetError('unexpected synthetic workspace')
        sides[trace_id] = {k: record[k] for k in ('trace_id', 'envelope', 'session', 'reference')}
        sides[trace_id].update(rules=evaluate_rules(envelope, config).model_dump(mode='json'),
                              rule_config_sha256=p['rule_config_sha256'])
    # Detect concurrent source changes before creating any outputs.
    if file_hash(pool / 'manifest.json') != pool_manifest_hash or any(
            file_hash(pool / name) != sha for name, sha in manifest['files'].items()):
        raise DatasetError('pool changed during partitioning')
    output.mkdir(parents=True, exist_ok=False)
    reports, hashes = {}, {}
    for name, members in splits.items():
        target = output / name
        target.mkdir()
        for filename, records in [('dataset.jsonl', members),
                                  ('replay.jsonl', [sides[r['trace_id']] for r in members])]:
            path = target / filename
            with path.open('x') as stream:
                stream.write(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in records))
            hashes[str(path.relative_to(output))] = file_hash(path)
        _, cases = validate_inputs(target / 'dataset.jsonl', target / 'replay.jsonl', p)
        reports[name] = {'rows': len(members), 'families': len({r['group_id'] for r in members}),
            'connected_groups': len(connected_groups(members)),
            'class_support': class_support(members, p['questions']),
            'rule_dispositions': dict(Counter(c.rules.disposition.value for c in cases))}
    access = access_probe([output / name / 'dataset.jsonl' for name in ('validation', 'calibration')])
    intake = {'status': 'pending_collection_and_isolation', 'human_label_owner': 'user',
        'collected_rows': 0, 'target_rows': 100, 'minimum_safe': 30, 'minimum_intervention': 30,
        'independent_synthetic_test': 'pending_external_reviewer',
        'instructions': [
            'Collect new real pre-action states with original envelopes, frozen rule outcomes and session counters.',
            'Redact before labeling. Exclude insufficient visible context; do not reconstruct missing history.',
            'User labels all seven questions and acceptable/forbidden actions before viewing model outputs.',
            'Record reviewer, rationale, family/session and collection identity; Astra suggestions remain frontier.',
            'Do not place final cases in this workspace or current chat before a separate inaccessible environment exists.',
            'Freeze candidates and protocol before the final custodian opens the test. No automatic promotion.']}
    write_json(output / 'test-intake.json', intake)
    hashes['test-intake.json'] = file_hash(output / 'test-intake.json')
    template = {'template_only': True, 'trace_id': None, 'reviewer': None, 'reviewed_at': None,
        'source': None, 'group_id': None, 'session_id': None, 'contrast_pair_id': None,
        'questions': p['questions'], 'labels': {key: None for key in p['questions']},
        'label_rationales': {key: None for key in p['questions']},
        'action_reference': {'source': None, 'requires_intervention': None, 'acceptable': [], 'forbidden': []},
        'review_status': 'pending', 'model_outputs_seen': False,
        'required_capture': ['exact_model_state', 'original_envelope', 'frozen_rules',
                             'rule_config_sha256', 'session_counters'],
        'note': 'Blank annotation sheet, not a trainable row. Fill source=human only after user review.'}
    write_json(output / 'human-label-template.json', template)
    hashes['human-label-template.json'] = file_hash(output / 'human-label-template.json')
    result = seal({'version': 1, 'kind': 'weight_space_partitions', 'status': 'open_development_only',
        'development_ready': True, 'blind_evaluation_ready': False,
        'protocol_sha256': p['sha256'], 'pool_manifest_sha256': pool_manifest_hash,
        'pool_path': str(pool.resolve()), 'files': hashes, 'partitions': reports,
        'goals': GOALS if goals is None else goals, 'history': history_manifest, 'audit': audit,
        'assignment': 'deterministic rare-label-first; support normalized by target group count; no predictions',
        'semantic_review': {'kind': 'author_self_review', 'links': SEMANTIC_LINKS,
            'goal_jaccard_threshold': 0.65, 'near_history_matches': similar,
            'near_match_policy': 'whole connected group development only',
            'limitations': 'Lexical screening cannot establish semantic independence; all new content was seen by Astra.'},
        'support_warnings': support_warnings(reports['train']['class_support'], reports['validation']['class_support']),
        'access': access, 'test': intake,
        'rule_capture': 'synthetic envelopes; current path resolver, no action execution or invented operational history',
        'source_hashes': {str(Path(__file__).resolve()): file_hash(Path(__file__))}})
    write_json(output / 'manifest.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('protocol', 'pool', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    result = freeze_pool(args.protocol, args.pool, args.output, root=Path(__file__).resolve().parents[2])
    print(json.dumps({'status': result['status'], 'sha256': result['sha256'],
                      'partitions': {k: {f: v[f] for f in ('rows', 'families', 'connected_groups')}
                                     for k, v in result['partitions'].items()}}))


if __name__ == '__main__':
    main()
