import copy

import pytest

from experiments.laya_weight_space.partitions import audit_splits, connected_groups, split_groups
from lgh.train.data import DatasetError
from tests.unit.test_train import make_row


def rows(n=8):
    result = []
    for i in range(n):
        r = make_row(i)
        r.update(group_id=f'g{i}', session_id=f's{i}', contrast_pair_id=f'p{i}', semantic_group=f'm{i}')
        result.append(r)
    return result


@pytest.mark.parametrize('key', ['trace_id', 'state', 'group_id', 'session_id', 'contrast_pair_id', 'semantic_group'])
def test_split_audit_rejects_every_identity_overlap(key):
    a, b = rows(2)
    b[key] = copy.deepcopy(a[key])
    with pytest.raises(DatasetError, match='overlap'):
        audit_splits({'train': [a], 'validation': [b]}, [])


def test_groups_are_transitive_across_session_family_and_pair():
    r = rows(4)
    r[1]['session_id'] = r[0]['session_id']
    r[2]['contrast_pair_id'] = r[1]['contrast_pair_id']
    groups = connected_groups(r)
    assert sorted(map(len, groups)) == [1, 3]


def test_partition_is_reproducible_and_never_splits_groups():
    r = rows(8)
    goals = dict(train=2, development=2, validation=2, calibration=2)
    first = split_groups(r, goals=goals)
    second = split_groups(list(reversed(r)), goals=goals)
    assert first == second
    assert all(len(value) == 2 for value in first.values())
    audit_splits(first, [])
    with pytest.raises(DatasetError, match='groups'):
        split_groups(r[:7], goals=goals)


def test_inherited_overlap_is_detected_even_without_legacy_group_ids():
    r = rows(2)
    legacy = {'trace_id': 'old-export', 'state': copy.deepcopy(r[0]['state'])}
    with pytest.raises(DatasetError, match='history'):
        audit_splits({'calibration': [r[0]]}, [legacy])


def test_known_development_groups_cannot_become_validation():
    r = rows(8)
    result = split_groups(r, goals=dict(train=2, development=2, validation=2, calibration=2),
                          development_only={'g0', 'g1'})
    assert {v['group_id'] for v in result['development']} == {'g0', 'g1'}


def test_lexical_neighbors_are_reported_without_using_labels():
    from experiments.laya_weight_space.partitions import near_matches, review_links
    r = review_links(rows(2))
    r[0]['state']['goal'] = 'Preserve the handwritten observations while replacing the archive.'
    r[1]['state']['goal'] = r[0]['state']['goal']
    matches = near_matches(r, [])
    assert len(matches) == 1 and matches[0]['historical_path'] is None
    history = {**r[1], 'trace_id': 'past-test', '_history_path': 'old-confirmation.jsonl'}
    assert near_matches([r[0]], [history])[0]['historical_path'] == 'old-confirmation.jsonl'


def test_development_only_restriction_propagates_through_connected_family():
    r = rows(10)
    r[0]['session_id'] = r[1]['session_id']
    result = split_groups(r, goals=dict(train=2, development=2, validation=2, calibration=2),
                          development_only={'g0'})
    development = {v['group_id'] for v in result['development']}
    assert {'g0', 'g1'} <= development


def test_expanded_curriculum_has_reviewed_groups_and_all_classes():
    from experiments.laya_weight_space.curriculum import FAMILIES
    from experiments.laya_weight_space.curriculum_ws04 import FAMILIES as NEW
    from experiments.laya_weight_space.build_dataset import prepare_pool
    from experiments.laya_weight_space.partitions import review_links
    from tests.unit.test_weight_space_data import TokenFixture
    from lgh.train.data import class_support
    from lgh.laya.questions import load_questions
    pool = review_links(prepare_pool(FAMILIES + NEW, TokenFixture())['rows'])
    groups = connected_groups(pool)
    assert len(groups) >= 75
    assert any(len({r['group_id'] for r in g}) > 1 for g in groups)
    splits = split_groups(pool)
    audit_splits(splits, [])
    for name, rows_ in splits.items():
        support = class_support(rows_, load_questions())
        assert all(n > 0 for counts in support.values() for n in counts.values()), (name, support)
    assert all(r['source'] == 'frontier' for r in pool)


def test_access_probe_does_not_claim_readable_data_is_isolated(tmp_path):
    from experiments.laya_weight_space.partitions import access_probe
    path = tmp_path / 'calibration.jsonl'
    path.write_text('[]\n')
    result = access_probe([path])
    assert result['isolated'] is False
    assert result['readable'][str(path)] is True


def test_freeze_pool_checks_hashes_and_captures_replay_without_execution(tmp_path, monkeypatch):
    from experiments.laya_weight_space import partitions, build_dataset
    from experiments.laya_weight_space.curriculum import FAMILIES
    from experiments.laya_weight_space.protocol import read_sealed
    from tests.unit.test_weight_space_data import TokenFixture
    from tests.unit.test_weight_space_evaluate import frozen_protocol
    protocol = frozen_protocol.__wrapped__(tmp_path, monkeypatch)
    from experiments.laya_weight_space.protocol import read_protocol
    p = read_protocol(protocol)
    monkeypatch.setattr(partitions, 'read_history', lambda root: ([], []))
    import subprocess
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('dataset action must not execute'))
    pool = tmp_path / 'pool'
    build_dataset.write_pool(build_dataset.prepare_pool(FAMILIES[:8], TokenFixture()), pool,
                             {'protocol_sha256': p['sha256'], 'source_hashes': {}})
    out = tmp_path / 'out'
    result = partitions.freeze_pool(protocol, pool, out, root=tmp_path,
        goals=dict(train=2, development=2, validation=2, calibration=2))
    assert result['status'] == 'open_development_only'
    assert result['blind_evaluation_ready'] is False
    assert result['test']['human_label_owner'] == 'user'
    assert result['test']['collected_rows'] == 0
    import json
    sheet = json.loads((out / 'human-label-template.json').read_text())
    assert sheet['template_only'] and sheet['source'] is None
    assert all(value is None for value in sheet['labels'].values())
    assert read_sealed(out / 'manifest.json') == result
    from experiments.laya_weight_space.protocol import validate_inputs
    for name in result['partitions']:
        rows_, cases = validate_inputs(out / name / 'dataset.jsonl', out / name / 'replay.jsonl', p)
        assert len(rows_) == len(cases) == 4
    with pytest.raises(DatasetError, match='exists'):
        partitions.freeze_pool(protocol, pool, out, root=tmp_path)
    (pool / 'pool.jsonl').write_text('{}\n')
    with pytest.raises(DatasetError, match='hash'):
        partitions.freeze_pool(protocol, pool, tmp_path / 'changed', root=tmp_path)
