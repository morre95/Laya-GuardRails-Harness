from lgh.eval.labels import append_label
from lgh.laya.questions import load_questions
from presentation.scripts import collect_metrics
from tests.unit.test_review import _label_body


def test_presentation_counts_only_current_usable_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_metrics, 'user_data_dir', lambda: tmp_path)
    append_label(_label_body(trace_id='good'), tmp_path)
    append_label(_label_body(trace_id='missing-goal'), tmp_path)
    append_label({'trace_id': 'missing-goal', 'source': 'human',
                  'review_status': 'insufficient_context', 'reason': 'Missing goal'}, tmp_path)
    result = collect_metrics.collect_labels(load_questions())
    assert result['traces'] == 1
    assert result['sources'] == {'human': 1}
    assert all(sum(counts.values()) == 1 for counts in result['distributions'].values())
