import copy
import json

import pytest

from experiments.laya_weight_space.curriculum import FAMILIES
from experiments.laya_weight_space.build_dataset import prepare_pool, write_pool
from lgh.laya.questions import load_questions
from lgh.train.data import DatasetError, load_rows


class TokenFixture:
    """Unit fixture only; the CLI always audits with the real checkpoint tokenizer."""
    def inspect(self, state, questions):
        return {'state_text': json.dumps(state, ensure_ascii=False), 'truncated': False,
                'questions': {key: {'tokens': 100, 'token_ids': [1, 2], 'decoded': 'fixture',
                                    'truncated': False} for key in questions}}


def test_pool_is_explicit_frontier_data_with_complete_contrasts_and_labels():
    result = prepare_pool(FAMILIES, TokenFixture())
    rows = result['rows']
    assert len({r['group_id'] for r in rows}) >= 30
    assert all(r['source'] == 'frontier' and r['provenance']['kind'] == 'synthetic' for r in rows)
    assert all(r['provenance']['review']['independent'] is False for r in rows)
    assert all(set(r['labels']) == set(load_questions()) == set(r['provenance']['label_rationales']) for r in rows)
    assert all(r['provenance']['partition'] == 'unassigned' for r in rows)
    assert all(len(r['state']['goal']) <= 400 for r in rows)
    counts = {}
    for row in rows:
        counts[row['group_id']] = counts.get(row['group_id'], 0) + 1
    assert all(n >= 2 for n in counts.values())
    for key, q in load_questions().items():
        actual = {row['labels'][key] for row in rows}
        assert actual == (set(q['criteria']) if q['type'] == 'choice' else {0, 1})


def test_authorization_does_not_change_physical_recoverability():
    result = prepare_pool(FAMILIES, TokenFixture())
    for family in FAMILIES:
        if family['dimension'] != 'authorization':
            continue
        rows = [r for r in result['rows'] if r['group_id'] == family['id']]
        assert len(rows) == 2
        assert rows[0]['state']['action'] == rows[1]['state']['action']
        for key in ('destructive_risk', 'sensitive_resource', 'external_impact', 'reversibility'):
            assert rows[0]['labels'][key] == rows[1]['labels'][key]


def test_clean_and_dirty_git_context_matches_explicit_scenario():
    rows = prepare_pool(FAMILIES, TokenFixture())['rows']
    pair = [r for r in rows if r['group_id'] == 'hard-reset-clean-versus-dirty']
    assert pair[0]['state']['repo']['dirty'] is False
    assert pair[1]['state']['repo']['dirty'] is True


def test_unseen_evidence_and_truncation_are_excluded_without_targets():
    family = copy.deepcopy(FAMILIES[0])
    family['variants'][0]['required_evidence'] = ['this text exists only in an omitted argument']
    result = prepare_pool([family], TokenFixture())
    assert any(r['reason'] == 'required_evidence_missing_from_model_state' for r in result['excluded'])
    assert all('labels' not in r for r in result['excluded'])

    class Truncated(TokenFixture):
        def inspect(self, state, questions):
            return {**super().inspect(state, questions), 'truncated': True}

    result = prepare_pool([FAMILIES[0]], Truncated())
    assert not result['rows']
    assert all(r['review_status'] == 'insufficient_context' for r in result['excluded'])


def test_missing_pair_member_does_not_leave_a_claimed_complete_contrast():
    family = copy.deepcopy(FAMILIES[0])
    family['variants'][0]['exclude_reason'] = 'fixture: missing context'
    result = prepare_pool([family], TokenFixture())
    assert not result['rows']
    assert len(result['excluded']) == 2
    assert any(r['reason'] == 'contrast_partner_excluded' for r in result['excluded'])


def test_context_exclusions_need_no_invented_labels():
    from experiments.laya_weight_space.curriculum import EXCLUDED_FAMILIES
    assert all(c['labels'] is None for f in EXCLUDED_FAMILIES for c in f['variants'])
    result = prepare_pool(EXCLUDED_FAMILIES, TokenFixture())
    assert not result['rows'] and len(result['excluded']) == 6
    family = copy.deepcopy(FAMILIES[0])
    family['variants'][0]['labels'] = None
    with pytest.raises(DatasetError, match='seven labels'):
        prepare_pool([family], TokenFixture())


def test_duplicate_visible_inputs_cannot_inflate_family_support():
    duplicate = copy.deepcopy(FAMILIES[0])
    duplicate['id'] = 'different-name-same-evidence'
    with pytest.raises(DatasetError, match='duplicate visible state'):
        prepare_pool([FAMILIES[0], duplicate], TokenFixture())


@pytest.mark.parametrize('mutation', ['labels', 'duplicate_family', 'rationale', 'authorization_invariant'])
def test_invalid_authored_data_fails_instead_of_becoming_training_rows(mutation):
    families = copy.deepcopy(FAMILIES)
    if mutation == 'labels': families[0]['variants'][0]['labels'].pop('handling')
    if mutation == 'duplicate_family': families.append(copy.deepcopy(families[0]))
    if mutation == 'rationale': families[0]['variants'][0]['rationale'] = ''
    if mutation == 'authorization_invariant':
        f = next(f for f in families if f['dimension'] == 'authorization')
        f['variants'][1]['labels']['reversibility'] = 'irreversible'
    with pytest.raises(DatasetError):
        prepare_pool(families, TokenFixture())


def test_exports_reload_and_do_not_overwrite_previous_artifacts(tmp_path):
    result = prepare_pool(FAMILIES, TokenFixture())
    out = tmp_path / 'pool'
    report = write_pool(result, out, {'tokenizer': 'unit fixture, not actual model evidence'})
    rows = load_rows(out / 'pool.jsonl')
    assert len(rows) == report['rows']
    assert report['partition_status'] == 'unassigned'
    assert report['human_review'] == 'pending'
    assert report['split_target']['minimum_total_families'] == 75
    assert report['split_target']['deficit'] == max(0, 75-report['families'])
    review = (out / 'review.md').read_text()
    assert all(row['trace_id'] in review for row in rows)
    assert 'fixture' in (out / 'model-inputs.jsonl').read_text()
    before = (out / 'pool.jsonl').read_bytes()
    with pytest.raises((FileExistsError, DatasetError)):
        write_pool(result, out, {})
    assert (out / 'pool.jsonl').read_bytes() == before


def test_native_tool_payload_is_not_silently_added_to_model_input():
    result = prepare_pool(FAMILIES, TokenFixture())
    native = next(r for r in result['rows'] if r['state']['action']['tool'] == 'write')
    assert 'command' not in native['state']['action']
    assert 'arguments' not in native['state']['action']
    record = next(r for r in result['envelopes'] if r['trace_id'] == native['trace_id'])
    assert 'content' in record['envelope']['action']['arguments']
    assert result['excluded']
    assert all(r['source'] == 'frontier' for r in result['excluded'])
