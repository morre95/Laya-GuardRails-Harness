import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lgh.eval.backends import HttpBackend
from lgh.eval.backend_contract import BackendSpec
from lgh.train.data import DatasetError
from tests.unit.test_backend_contract import answers, case, experiment


@pytest.fixture
def server():
    received = []
    response = {'payload': {}, 'status': 200, 'redirect': None, 'raw': None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.reply()
        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.reply()
        def reply(self):
            self.send_response(response['status'])
            if response['redirect']: self.send_header('Location', response['redirect'])
            self.end_headers()
            self.wfile.write(response['raw'] if response['raw'] is not None else json.dumps(response['payload']).encode())

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}', received, response
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.mark.parametrize('kind,endpoint', [('laya','/predict'), ('kev','/v1/systemone')])
def test_http_sends_only_frozen_model_inputs(server, kind, endpoint):
    url, received, response = server
    row, _ = case()
    spec = experiment().backends['kev' if kind == 'kev' else 'laya_current'].model_copy(update={'url': url})
    response['payload'] = {'answers': answers(row), 'latency_ms': 12, 'model': 'kev-latest' if kind == 'kev' else spec.model}
    result = HttpBackend(spec, timeout=1).predict(row['state'], row['questions'])
    path, body = received[0]
    assert path == endpoint
    assert body['state'] == row['state']
    assert body['questions'] == row['questions']
    assert set(body) == ({'state','questions','model'} if kind == 'kev' else {'state','questions'})
    assert result['answers']['handling']['probabilities']['allow'] == 0.97
    assert result['server_latency_ms'] == 12
    assert result['client_latency_ms'] >= 0


@pytest.mark.parametrize('error', ['http', 'json', 'truncated', 'identity', 'invalid', 'redirect'])
def test_http_failures_do_not_become_predictions(server, error):
    url, received, response = server
    row, _ = case()
    spec = experiment().backends['laya_current'].model_copy(update={'url': url})
    response['payload'] = {'answers': answers(row), 'model': spec.model}
    if error == 'http': response['status'] = 422
    if error == 'json': response['raw'] = b'not-json'
    if error == 'truncated': response['payload']['truncated'] = True
    if error == 'identity': response['payload']['model'] = 'other-checkpoint'
    if error == 'invalid': response['payload']['answers'].pop('handling')
    if error == 'redirect':
        response['status'] = 302
        response['redirect'] = 'http://example.org/should-never-be-followed'
    with pytest.raises(DatasetError):
        HttpBackend(spec, timeout=1).predict(row['state'], row['questions'])
    assert len(received) == 1


@pytest.mark.parametrize('url', ['http://example.org:8009', 'http://localhost:8009',
                               'http://127.0.0.1:8009/path', 'http://user:password@127.0.0.1:8009'])
def test_nonlocal_or_credential_endpoints_rejected(url):
    with pytest.raises(ValueError):
        BackendSpec(kind='laya', url=url, model='m')


def test_readiness_detects_cuda_dtype_and_checkpoint_fallback(server):
    url, _, response = server
    spec = experiment().backends['kev'].model_copy(update={'url': url})
    card = {'run': spec.model, 'device': 'cuda', 'dtype': 'torch.bfloat16', 'truncate_states': False}
    response['payload'] = {'models': [{'name': 'kev-latest', **card}]}
    assert HttpBackend(spec).identity()['observed']['run'] == spec.model
    for key, value in [('run','other'), ('device','cpu'), ('dtype','torch.float32'), ('truncate_states',True)]:
        response['payload'] = {'models': [{'name':'kev-latest', **card, key: value}]}
        with pytest.raises(DatasetError): HttpBackend(spec).identity()


def test_client_latency_has_a_controlled_boundary(server):
    url, _, response = server
    row, _ = case()
    spec = experiment().backends['laya_current'].model_copy(update={'url':url})
    response['payload'] = {'answers':answers(row), 'model':spec.model, 'latency_ms':99}
    ticks = iter([1.0, 1.125])
    result = HttpBackend(spec, clock=lambda: next(ticks)).predict(row['state'], row['questions'])
    assert result['client_latency_ms'] == 125
    assert result['server_latency_ms'] == 99


def test_timeout_is_an_explicit_failure(monkeypatch):
    row, _ = case()
    client = HttpBackend(experiment().backends['kev'])
    def timeout(*args, **kwargs): raise TimeoutError('deliberate timeout')
    monkeypatch.setattr(client.opener, 'open', timeout)
    with pytest.raises(DatasetError, match='HTTP request failed'):
        client.predict(row['state'], row['questions'])
