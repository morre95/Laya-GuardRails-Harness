"""Frozen inputs and strict boundaries for offline backend comparisons."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, StrictBool, model_validator

from lgh.config.models import GuardrailConfig
from lgh.eval.compare import read_dataset
from lgh.laya.client import state_payload
from lgh.laya.questions import load_questions
from lgh.resources import read_package_text
from lgh.schema.base import FrozenModel
from lgh.schema.decision import GuardrailDecision
from lgh.schema.envelope import ActionEnvelope
from lgh.schema.rules import DISPOSITION_RANK, RuleResult
from lgh.state.builder import build_laya_state
from lgh.state.redact import redact_text
from lgh.train.data import DatasetError

KEV_MODEL = 'jaredpalmer/kev-4b@v1.0'
SOURCES = ('human', 'frontier', 'deterministic')


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatasetError('probability must be a finite number')
    p = float(value)
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise DatasetError('probability must be finite and between 0 and 1')
    return p


def ensure_redacted(value: Any) -> None:
    """Reject known credential patterns before freezing the full replay envelope.

    This complements independent review; it cannot identify every possible secret.
    """
    if isinstance(value, str) and redact_text(value) != value:
        raise DatasetError('replay context must redact credential values before collection')
    if isinstance(value, list):
        for item in value:
            ensure_redacted(item)
    if isinstance(value, dict):
        for key, item in value.items():
            if (re.fullmatch(r'api[_-]?key|secret|token|password|passwd|authorization', key, re.I)
                    and item not in (None, '', '[REDACTED]', '[REDACTED_PRIVATE_KEY]')):
                raise DatasetError('replay context must redact credential fields before collection')
            ensure_redacted(item)


def loopback_url(url: str) -> str:
    parsed = urlsplit(url)
    try:
        local = ipaddress.ip_address(parsed.hostname or '').is_loopback
        port = parsed.port
    except ValueError as exc:
        raise DatasetError('endpoint must use a literal loopback address') from exc
    if (not local or parsed.scheme != 'http' or not port or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise DatasetError('endpoint must be a plain loopback HTTP URL with explicit port')
    return url.rstrip('/')


class BackendSpec(FrozenModel):
    kind: Literal['laya', 'kev']
    url: str
    model: str = Field(min_length=1)
    revision: str | None = None
    code_revision: str | None = None
    device: str | None = None
    dtype: str | None = None
    quantized: StrictBool = False
    temperatures: dict[str, float] = Field(default_factory=dict)
    provenance: Literal['released', 'local_finetuned', 'unknown'] = 'unknown'
    training_dataset: str | None = None
    training_dataset_sha256: str | None = None
    runtime: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_backend(self):
        loopback_url(self.url)
        for temperature in self.temperatures.values():
            if not math.isfinite(temperature) or temperature <= 0:
                raise ValueError('temperatures must be finite and positive')
        if self.kind == 'kev' and (self.model != KEV_MODEL or self.device != 'cuda'
                                  or self.dtype not in ('bf16', 'bfloat16')
                                  or self.quantized or self.temperatures):
            raise ValueError('Kev must use kev-4b@v1.0 on CUDA/BF16 without quantization or LGH temperatures')
        return self


class Experiment(FrozenModel):
    version: Literal[1]
    purpose: Literal['benchmark', 'synthetic_smoke'] = 'benchmark'
    config: GuardrailConfig
    hardware: dict[str, Any]
    backends: dict[str, BackendSpec]
    warmup: int = Field(default=1, ge=1, le=100)
    repetitions: int = Field(default=3, ge=1, le=100)

    @model_validator(mode='before')
    @classmethod
    def strict_config(cls, data):
        if isinstance(data, dict) and isinstance(data.get('config'), dict):
            # GuardrailConfig intentionally ignores extras for live configuration;
            # benchmark snapshots must not silently discard a misspelled threshold.
            def check(value, model):
                known = {name for name in type(model).model_fields}
                known.update(f.alias for f in type(model).model_fields.values() if f.alias)
                if set(value) - known:
                    raise ValueError(f'unknown config fields: {sorted(set(value) - known)}')
                for key, item in value.items():
                    nested = getattr(model, key, None)
                    if isinstance(item, dict) and hasattr(type(nested), 'model_fields'):
                        check(item, nested)
            check(data['config'], GuardrailConfig())
        return data

    @model_validator(mode='after')
    def valid_experiment(self):
        if set(self.backends) not in ({'laya_current', 'kev'}, {'laya_current', 'kev', 'laya_released'}):
            raise ValueError('backends must contain laya_current, kev and optional laya_released')
        current = self.backends['laya_current']
        if current.kind != 'laya' or self.backends['kev'].kind != 'kev':
            raise ValueError('backend names must match their kinds')
        if current.model != self.config.laya.model or current.temperatures != self.config.laya.temperatures:
            raise ValueError('current Laya must match the frozen model and effective temperatures')
        if 'laya_released' in self.backends:
            released = self.backends['laya_released']
            if released.kind != 'laya' or released.model != 'convaiinnovations/laya-typed-decisions':
                raise ValueError('released Laya must use the released baseline')
        elif current.model != 'convaiinnovations/laya-typed-decisions':
            raise ValueError('a distinct released Laya baseline is required')
        for value in self.config.laya.thresholds.model_dump().values():
            probability(value)
        return self

    def backend_names(self) -> list[str]:
        names = ['laya_current', 'kev']
        released = self.backends.get('laya_released')
        current = self.backends['laya_current']
        if released and (released.model, released.revision, released.temperatures) != (
                current.model, current.revision, current.temperatures):
            names.append('laya_released')
        return names


class ActionReference(FrozenModel):
    source: Literal['human', 'frontier', 'deterministic']
    requires_intervention: StrictBool
    acceptable: list[GuardrailDecision] = Field(min_length=1)
    forbidden: list[GuardrailDecision]

    @model_validator(mode='after')
    def valid_reference(self):
        if set(self.acceptable) & set(self.forbidden):
            raise ValueError('acceptable and forbidden references overlap')
        if self.requires_intervention and GuardrailDecision.ALLOW in self.acceptable:
            raise ValueError('a risky action cannot accept direct ALLOW')
        if not self.requires_intervention and self.acceptable != [GuardrailDecision.ALLOW]:
            raise ValueError('a safe action must accept only direct ALLOW')
        return self


class ReplayCase(FrozenModel):
    trace_id: str = Field(min_length=1)
    envelope: ActionEnvelope
    rules: RuleResult
    rule_config_sha256: str
    session: dict[str, Any]
    reference: ActionReference | None = None

    @model_validator(mode='after')
    def valid_snapshot(self):
        counters = self.session.get('counters')
        if not isinstance(counters, dict):
            raise ValueError('session must contain frozen counters')
        for slot in counters.values():
            if not isinstance(slot, dict) or set(slot) != {'verification', 'replan', 'frontier'}:
                raise ValueError('each counter needs verification, replan and frontier')
            if any(type(n) is not int or n < 0 for n in slot.values()):
                raise ValueError('session counters must be nonnegative integers')
        if self.rules.matched:
            strongest = max((m.disposition for m in self.rules.matched), key=DISPOSITION_RANK.__getitem__)
            if strongest != self.rules.disposition:
                raise ValueError('rule disposition does not match frozen rule matches')
        elif self.rules.disposition.value != 'PASS':
            raise ValueError('non-PASS rules require matches')
        return self


def rule_config_hash(config: GuardrailConfig) -> str:
    return digest({'config': config.model_dump(mode='json'),
                   'builtin_rules': read_package_text('rules', 'builtin_rules.yaml')})


def read_inputs(dataset: Path, replay: Path, experiment: Experiment, *, labels: Path | None = None,
                unlabeled: bool = False) -> tuple[list[dict], list[ReplayCase]]:
    try:
        rows = read_dataset(dataset, labels=labels, unlabeled=unlabeled)
        expected = load_questions()
        # Mapping equality ignores insertion order; option order affects inference.
        expected_signature = [(k, q['type'], list(q.get('criteria', {}))) for k, q in expected.items()]
        for row in rows:
            signature = [(k, q['type'], list(q.get('criteria', {}))) for k, q in row['questions'].items()]
            if row['questions'] != expected or signature != expected_signature:
                raise DatasetError('dataset must use the exact v0.1 questions and option order')
        records = [json.loads(line) for line in replay.read_text().splitlines() if line.strip()]
        if unlabeled:
            records = [{**r, 'reference': None} for r in records]
        cases = [ReplayCase.model_validate(r) for r in records]
        by_id = {c.trace_id: c for c in cases}
        if len(by_id) != len(cases) or set(by_id) != {r['trace_id'] for r in rows}:
            raise DatasetError('replay must join dataset exactly once per trace_id')
        config_hash = rule_config_hash(experiment.config)
        ordered = []
        for row in rows:
            c = by_id[row['trace_id']]
            ensure_redacted(c.envelope.model_dump(mode='json'))
            if c.rule_config_sha256 != config_hash:
                raise DatasetError(f'{c.trace_id}: frozen rule/config hash mismatch')
            if state_payload(build_laya_state(c.envelope)) != row['state']:
                raise DatasetError(f'{c.trace_id}: envelope does not reproduce frozen state')
            if not unlabeled and c.reference is None:
                raise DatasetError(f'{c.trace_id}: independent action reference required')
            ordered.append(c)
        return rows, ordered
    except (KeyError, TypeError, ValueError) as exc:
        raise DatasetError(f'invalid comparison input: {exc}') from exc


def validate_answers(answers: Any, questions: dict) -> dict:
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise DatasetError('answer questions do not match the frozen question set')
    for key, question in questions.items():
        a = answers[key]
        if not isinstance(a, dict) or a.get('type') != question['type']:
            raise DatasetError(f'{key}: answer type mismatch')
        if question['type'] == 'noul':
            probability(a.get('noul'))
        else:
            probs = a.get('probabilities')
            if not isinstance(probs, dict) or set(probs) != set(question['criteria']):
                raise DatasetError(f'{key}: option mismatch')
            values = {k: probability(probs[k]) for k in question['criteria']}
            if abs(sum(values.values()) - 1) > 0.001:
                raise DatasetError(f'{key}: probabilities do not sum to one')
            choice = a.get('choice')
            # Rounding can produce tied maxima; vendor tie selection may differ.
            if choice not in values or values[choice] != max(values.values()):
                raise DatasetError(f'{key}: choice is inconsistent with probabilities')
    return answers
