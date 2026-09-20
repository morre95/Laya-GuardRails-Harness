from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from lgh.laya.normalize import LayaUnavailable, normalize_assessment
from lgh.laya.questions import load_questions
from lgh.schema.envelope import LayaState
from lgh.schema.laya import LayaAssessment


class LayaClient(Protocol):
    def assess(self, state: LayaState) -> LayaAssessment:
        ...


class HttpLayaClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        timeout: float = 3.0,
        model: str = "convaiinnovations/laya-typed-decisions",
        temperatures: dict[str, float] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.model = model
        self.temperatures = temperatures or {}
        self.questions = load_questions()

    def assess(self, state: LayaState) -> LayaAssessment:
        payload = {
            "state": state.model_dump(mode="json", exclude_none=True),
            "questions": self.questions,
        }
        request = urllib.request.Request(
            self.base_url + "/predict",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LayaUnavailable(str(exc)) from exc
        model = body.get("model") or self.model
        latency = float(body.get("latency_ms") or body.get("latencyMs") or 0.0)
        return normalize_assessment(
            body,
            model=model,
            latency_ms=latency,
            temperatures=self.temperatures,
        )


class FakeLayaClient:
    def __init__(self, assessment: LayaAssessment | dict[str, Any] | None = None) -> None:
        self.assessment = assessment
        self.calls: list[LayaState] = []

    def assess(self, state: LayaState) -> LayaAssessment:
        self.calls.append(state)
        if self.assessment is None:
            raise LayaUnavailable("no mock assessment configured")
        if isinstance(self.assessment, LayaAssessment):
            return self.assessment
        if "answers" in self.assessment or "task_alignment" in self.assessment:
            return normalize_assessment(
                self.assessment if "answers" in self.assessment else {"answers": self.assessment},
                model="fake",
                latency_ms=0.0,
            )
        return LayaAssessment.model_validate(self.assessment)
