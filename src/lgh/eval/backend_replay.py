"""Replay fixed assessments through production policy without external effects."""
from __future__ import annotations

from copy import deepcopy
import time
from collections.abc import Callable

from lgh.eval.backend_contract import Experiment, ReplayCase, validate_answers
from lgh.frontier.stub import FrontierUnavailable, StubReviewer
from lgh.laya.client import FakeLayaClient
from lgh.laya.normalize import normalize_assessment
from lgh.pipeline import Pipeline
from lgh.schema.decision import Mode
from lgh.schema.envelope import LayaState
from lgh.schema.rules import RuleDisposition
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter, build_trace
from lgh.train.data import DatasetError


class _MemorySessions(SessionStore):
    def __init__(self, snapshot: dict):
        self.data = deepcopy(snapshot)

    def load(self, session_id: str) -> dict:
        return deepcopy(self.data)

    def save(self, session_id: str, data: dict) -> None:
        self.data = deepcopy(data)


class _MemoryTraces(TraceWriter):
    def __init__(self):
        pass

    def write(self, **kwargs):
        return build_trace(**kwargs)


class _OfflineReviewer(StubReviewer):
    expected_error: str | None = None

    def review(self, request):
        try:
            return super().review(request)
        except FrontierUnavailable as exc:
            self.expected_error = str(exc)
            raise


def replay_assessment(row: dict, case: ReplayCase, experiment: Experiment, backend: str,
                      answers: dict, *, clock: Callable[[], float] = time.perf_counter) -> dict:
    started = clock()
    spec = experiment.backends[backend]
    model_dependent = case.rules.disposition == RuleDisposition.PASS
    validate_answers(answers, row['questions'])
    assessment = None
    if model_dependent:
        assessment = normalize_assessment({'answers': answers}, model=spec.model, latency_ms=0,
                                          temperatures=spec.temperatures)
    config = experiment.config.model_copy(deep=True)
    # An explicit simulation setting, never written to the live config. This
    # makes unresolved reviews pending-human instead of shadow-mode passthrough.
    config.mode = Mode.ENFORCE
    sessions = _MemorySessions(case.session)
    reviewer = _OfflineReviewer(unavailable=True)
    pipe = Pipeline(config, laya=FakeLayaClient(assessment),
                    reviewer=reviewer,
                    sessions=sessions, traces=_MemoryTraces())
    result = pipe.evaluate(case.envelope, frozen_state=LayaState.model_validate(row['state']),
                           frozen_rules=case.rules)
    if result.trace.laya is not None and result.laya is None:
        raise DatasetError('replay lost model assessment')
    # Pipeline normally fails closed on internal errors. Benchmark bookkeeping
    # must expose them, not count a fail-closed decision as model correctness.
    expected_review_error = (reviewer.expected_error is not None
                             and result.error == reviewer.expected_error)
    if result.error is not None and not expected_review_error:
        raise DatasetError(f'{case.trace_id}: offline replay failed: {result.error}')
    return {
        'trace_id': row['trace_id'], 'backend': backend,
        'model_dependent': model_dependent,
        'rules': case.rules.model_dump(mode='json'),
        'assessment': assessment.model_dump(mode='json') if assessment else None,
        'policy_decision': result.policy_decision.value,
        'final_decision': result.decision.value,
        'reference': case.reference.model_dump(mode='json') if case.reference else None,
        'replay_latency_ms': (clock() - started) * 1000,
        'snapshot_mode': experiment.config.mode.value, 'replay_mode': 'enforce',
        'reviewer': 'unavailable', 'approval_granted': False, 'executed': False,
    }
