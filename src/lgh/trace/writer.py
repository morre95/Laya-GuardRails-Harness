from __future__ import annotations

import fcntl
from pathlib import Path

from lgh.ids import new_id, utc_now_iso
from lgh.paths import traces_dir
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.envelope import ActionEnvelope, LayaState
from lgh.schema.laya import LayaAssessment
from lgh.schema.rules import RuleResult
from lgh.schema.trace import (
    DecisionTrace,
    FrontierTrace,
    HumanTrace,
    LayaTrace,
    Outcome,
    RuleEvaluation,
)
from lgh.state.redact import is_sensitive_target
from lgh.trace.hashing import canonical_json, envelope_hash
from lgh.trace.reader import last_record_hash


def build_trace(
    *,
    envelope: ActionEnvelope,
    rules: RuleResult,
    policy_decision: GuardrailDecision,
    final_decision: GuardrailDecision,
    mode: Mode,
    laya: LayaAssessment | None = None,
    laya_error: str | None = None,
    frontier: FrontierTrace | None = None,
    human: HumanTrace | None = None,
    verification_skill: str | None = None,
    outcome: Outcome | None = None,
    error: str | None = None,
    prev_hash: str | None = None,
    state: LayaState | None = None,
) -> DecisionTrace:
    laya_trace = None
    if laya is not None:
        laya_trace = LayaTrace(model=laya.model, assessment=laya, error=laya_error)
    elif laya_error:
        # Minimal placeholder is omitted; error stored on the trace root.
        pass
    return DecisionTrace(
        traceId=new_id(),
        timestamp=utc_now_iso(),
        envelopeHash=envelope_hash(envelope),
        prevHash=prev_hash,
        ruleEvaluation=RuleEvaluation(
            matched=[item.id for item in rules.matched],
            disposition=str(rules.disposition),
        ),
        laya=laya_trace,
        state=state,
        policyDecision=policy_decision,
        frontier=frontier,
        human=human,
        verificationSkill=verification_skill,
        finalDecision=final_decision,
        outcome=outcome,
        error=laya_error or error,
        contentsLogged=False if is_sensitive_target(envelope.action.target) else False,
        mode=str(mode),
    )


class TraceWriter:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or traces_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, trace: DecisionTrace) -> Path:
        path = self.directory / f"{trace.timestamp[:10]}.jsonl"
        payload = trace.model_dump(mode="json", by_alias=True)
        line = canonical_json(payload)
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(line + "\n")
        return path

    def write(
        self,
        *,
        envelope: ActionEnvelope,
        rules: RuleResult,
        policy_decision: GuardrailDecision,
        final_decision: GuardrailDecision,
        mode: Mode,
        **kwargs,
    ) -> DecisionTrace:
        prev = last_record_hash(self.directory)
        trace = build_trace(
            envelope=envelope,
            rules=rules,
            policy_decision=policy_decision,
            final_decision=final_decision,
            mode=mode,
            prev_hash=prev,
            **kwargs,
        )
        self.append(trace)
        return trace
