import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lgh.eval.export_dataset import export_dataset
from lgh.eval.labels import append_label, load_labels, load_review_exclusions
from lgh.review.queue import ReviewStore
from lgh.review.server import make_handler
from lgh.trace.reader import iter_traces
from tests.unit.test_review import _label_body, _pipe


def test_exclusion_removes_previously_labeled_case_without_rewriting_trace(tmp_path):
    pipe, env = _pipe(tmp_path)
    result = pipe.evaluate(env)
    tid = result.trace.trace_id
    trace_files = {p: p.read_bytes() for p in (tmp_path / 't').glob('*.jsonl')}
    append_label(_label_body(trace_id=tid), tmp_path)
    assert len(export_dataset(list(iter_traces(tmp_path / 't')), load_labels(tmp_path))) == 1
    append_label({'trace_id': tid, 'source': 'human', 'review_status': 'insufficient_context',
                  'reason': 'The goal is a tool result'}, tmp_path)
    assert load_labels(tmp_path) == []
    assert load_review_exclusions(tmp_path)[tid]['reason'] == 'The goal is a tool result'
    assert export_dataset(list(iter_traces(tmp_path / 't')), load_labels(tmp_path)) == []
    store = ReviewStore(traces_dir=tmp_path / 't', data_dir=tmp_path)
    assert store.items()[0]['status'] == 'insufficient_context'
    assert store.counts()['insufficient_context'] == 1
    assert store.payload(tid)['quality']['reason'] == 'The goal is a tool result'
    assert all(p.read_bytes() == data for p, data in trace_files.items())
    append_label(_label_body(trace_id=tid, task_alignment='supporting'), tmp_path)
    assert load_review_exclusions(tmp_path) == {}
    assert store.items()[0]['status'] == 'labeled'
    assert export_dataset(list(iter_traces(tmp_path / 't')), load_labels(tmp_path))[0]['labels']['task_alignment'] == 'supporting'


def test_export_does_not_treat_quality_marker_as_a_label(tmp_path):
    pipe, env = _pipe(tmp_path)
    trace = pipe.evaluate(env).trace
    marker = {'trace_id': trace.trace_id, 'source': 'human',
              'review_status': 'insufficient_context', 'reason': 'Missing goal'}
    assert export_dataset([trace], [_label_body(trace_id=trace.trace_id), marker]) == []


def test_quality_endpoint_validates_trace_and_reason_and_keeps_teacher_input_exact(tmp_path):
    pipe, env = _pipe(tmp_path)
    tid = pipe.evaluate(env).trace.trace_id
    store = ReviewStore(traces_dir=tmp_path / 't', data_dir=tmp_path)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store))
    Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'

    def post(payload):
        req = Request(base + '/api/quality', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
        return json.loads(urlopen(req, timeout=2).read())

    try:
        for payload, code in [({'trace_id': tid, 'reason': ''}, 400),
                              ({'trace_id': 'missing', 'reason': 'missing goal'}, 404),
                              ({'trace_id': tid, 'reason': 'x' * 1001}, 400)]:
            with pytest.raises(HTTPError) as exc:
                post(payload)
            assert exc.value.code == code
        saved = post({'trace_id': tid, 'reason': 'Missing goal token=secret-value'})
        assert saved['ok'] is True
        assert store.items()[0]['status'] == 'insufficient_context'
        assert 'secret-value' not in json.dumps(store.payload(tid)['quality'])
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_calibration_ignores_quality_markers(tmp_path):
    from lgh.eval.calibrate import calibrate_from_traces
    pipe, env = _pipe(tmp_path)
    trace = pipe.evaluate(env).trace
    marker = {'trace_id': trace.trace_id, 'source': 'human',
              'review_status': 'insufficient_context', 'reason': 'Missing goal'}
    assert calibrate_from_traces([trace], [marker]) == {'report': {}, 'temperatures': {}}


def test_review_and_export_keep_model_input_separate_from_source_context(tmp_path):
    from lgh.schema.envelope import InstructionContext
    from lgh.laya.client import state_payload
    pipe, env = _pipe(tmp_path, goal='Fix routes', command='echo hello')
    env = env.model_copy(update={'task': env.task.model_copy(update={
        'instruction_context': InstructionContext(messages=['Fix routes and preserve backwards compatibility'])})})
    trace = pipe.evaluate(env).trace
    store = ReviewStore(traces_dir=tmp_path / 't', data_dir=tmp_path)
    payload = store.payload(trace.trace_id)
    assert payload['state'] == state_payload(trace.state)
    assert payload['reviewContext']['instructions']['messages'] == ['Fix routes and preserve backwards compatibility']
    append_label(_label_body(trace_id=trace.trace_id), tmp_path)
    exported = export_dataset(list(iter_traces(tmp_path / 't')), load_labels(tmp_path))[0]
    assert exported['state'] == state_payload(trace.state)
    assert 'reviewContext' not in exported
    assert 'instructions' not in exported['state']
