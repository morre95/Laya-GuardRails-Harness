"""Small loopback-only HTTP adapters; never send benchmark references."""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from lgh.eval.backend_contract import BackendSpec, loopback_url, validate_answers
from lgh.train.data import DatasetError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpBackend:
    def __init__(self, spec: BackendSpec, *, timeout: float = 30,
                 clock: Callable[[], float] = time.perf_counter):
        if not math.isfinite(timeout) or timeout <= 0:
            raise DatasetError('timeout must be finite and positive')
        self.spec = spec
        self.base_url = loopback_url(spec.url)
        self.timeout = timeout
        self.clock = clock
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
            headers={'Content-Type': 'application/json'},
            method='GET' if payload is None else 'POST',
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise DatasetError('backend response exceeds 16 MiB')
                body = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise DatasetError(f'{self.spec.kind} HTTP request failed ({type(exc).__name__})') from exc
        if not isinstance(body, dict):
            raise DatasetError('backend response must be a JSON object')
        return body

    def identity(self) -> dict:
        if self.spec.kind == 'laya':
            observed = self._request('/health')
            if observed.get('ok') is not True or observed.get('model') != self.spec.model:
                raise DatasetError('Laya is not ready or serves a different checkpoint')
        else:
            body = self._request('/v1/models')
            cards = body.get('models')
            if not isinstance(cards, list):
                raise DatasetError('Kev readiness response lacks model cards')
            observed = next((c for c in cards if isinstance(c, dict) and c.get('name') == 'kev-latest'), None)
            if observed is None or observed.get('run') != self.spec.model:
                raise DatasetError('Kev serves a different checkpoint; pinned v1.0 required')
            if (not str(observed.get('device', '')).startswith('cuda')
                    or observed.get('dtype') not in ('bf16', 'bfloat16', 'torch.bfloat16')
                    or observed.get('truncate_states') is not False):
                raise DatasetError('Kev must serve CUDA/BF16 without truncation')
        return {'observed': observed, 'declared': self.spec.model_dump(mode='json'),
                'revision_verification': 'operator_supplied; endpoint does not verify weight hashes'}

    def predict(self, state: dict, questions: dict) -> dict[str, Any]:
        payload = {'state': state, 'questions': questions}
        if self.spec.kind == 'kev':
            payload['model'] = 'kev-latest'  # API routing alias, never checkpoint identity.
        started = self.clock()
        body = self._request('/predict' if self.spec.kind == 'laya' else '/v1/systemone', payload)
        elapsed = (self.clock() - started) * 1000
        usage = body.get('usage') or {}
        if (body.get('truncated') is True
                or (isinstance(usage, dict) and isinstance(usage.get('state_tokens'), (int, float))
                    and isinstance(usage.get('state_tokens_used'), (int, float))
                    and usage['state_tokens_used'] < usage['state_tokens'])):
            raise DatasetError('backend truncated the frozen input')
        expected = self.spec.model if self.spec.kind == 'laya' else 'kev-latest'
        if body.get('model') != expected:
            raise DatasetError('prediction model identity changed or is missing')
        validated = validate_answers(body.get('answers'), questions)
        server_ms = body.get('latency_ms')
        if server_ms is not None and (isinstance(server_ms, bool) or not isinstance(server_ms, (int, float))
                                      or not math.isfinite(server_ms) or server_ms < 0):
            raise DatasetError('invalid server latency')
        return {'answers': validated, 'client_latency_ms': elapsed,
                'server_latency_ms': server_ms, 'usage': usage,
                'prefix_cache_hit': body.get('prefix_cache_hit')}
