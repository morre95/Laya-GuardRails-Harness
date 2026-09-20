from __future__ import annotations

import json
import shutil
import subprocess

from lgh.frontier.stub import FrontierUnavailable
from lgh.schema.frontier import ReviewRequest, ReviewResponse

SYSTEM = (
    "You are a classifier, not an executor. Do not run tools. "
    "Return ONLY JSON with keys decision, reason, verificationSkill. "
    "decision must be one of ALLOW, VERIFY, REPLAN, HUMAN_REQUIRED, BLOCK. "
    "reason max 300 characters. Do not propose commands."
)


class ClaudeCliReviewer:
    def __init__(self, timeout: float = 20.0, binary: str = "claude") -> None:
        self.timeout = timeout
        self.binary = binary

    def review(self, request: ReviewRequest) -> ReviewResponse:
        if shutil.which(self.binary) is None:
            raise FrontierUnavailable(f"{self.binary} not on PATH")
        payload = request.model_dump(mode="json", by_alias=True)
        prompt = (
            SYSTEM
            + "\n\nReview this proposed coding-agent action and classify it.\n\n"
            + json.dumps(payload, indent=2)
        )
        try:
            completed = subprocess.run(
                [self.binary, "-p", prompt, "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FrontierUnavailable(str(exc)) from exc
        if completed.returncode != 0:
            raise FrontierUnavailable(completed.stderr[-400:] or "claude failed")
        raw = completed.stdout.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FrontierUnavailable("invalid json from claude") from exc
        if isinstance(data, dict) and "result" in data and isinstance(data["result"], str):
            try:
                data = json.loads(data["result"])
            except json.JSONDecodeError as exc:
                raise FrontierUnavailable("invalid nested json from claude") from exc
        if not isinstance(data, dict):
            raise FrontierUnavailable("unexpected claude payload")
        reason = str(data.get("reason") or "")[:300]
        skill = data.get("verificationSkill") or data.get("verification_skill")
        decision = str(data.get("decision") or "")
        try:
            return ReviewResponse(decision=decision, reason=reason, verificationSkill=skill)  # type: ignore[arg-type]
        except Exception as exc:
            raise FrontierUnavailable(str(exc)) from exc
