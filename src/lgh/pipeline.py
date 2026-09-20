from __future__ import annotations

from dataclasses import dataclass

from lgh.config.models import GuardrailConfig
from lgh.frontier.base import map_frontier
from lgh.frontier.claude_cli import ClaudeCliReviewer
from lgh.frontier.stub import FrontierUnavailable, StubReviewer
from lgh.human.prompt import human_prompt
from lgh.laya.client import HttpLayaClient, LayaClient
from lgh.laya.normalize import LayaUnavailable
from lgh.policy.reducer import reduce_decision
from lgh.rules.engine import evaluate_rules, is_known_safe, matched_categories
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.envelope import ActionEnvelope
from lgh.schema.frontier import ReviewRequest, ReviewResponse
from lgh.schema.laya import LayaAssessment
from lgh.schema.rules import RuleDisposition, RuleResult
from lgh.schema.trace import DecisionTrace, FrontierTrace, HumanTrace
from lgh.schema.verification import VerificationDirective
from lgh.session.antiloop import action_key, apply_antiloop
from lgh.session.store import SessionStore
from lgh.state.builder import apply_environment, build_laya_state
from lgh.trace.writer import TraceWriter
from lgh.verification.router import route_verification

RISKY_TOOLS = {"shell", "write", "edit", "git", "database", "network", "mcp"}


@dataclass
class EvaluationResult:
    envelope: ActionEnvelope
    rules: RuleResult
    decision: GuardrailDecision
    policy_decision: GuardrailDecision
    laya: LayaAssessment | None
    frontier: ReviewResponse | None
    verification: VerificationDirective | None
    human_prompt_text: str | None
    trace: DecisionTrace
    error: str | None
    mode: Mode


def effective_mode(config: GuardrailConfig, rules: RuleResult, envelope: ActionEnvelope) -> Mode:
    if config.mode == Mode.ENFORCE:
        return Mode.ENFORCE
    categories = set(config.enforce_categories)
    if categories & matched_categories(rules) or envelope.action.tool in categories:
        return Mode.ENFORCE
    return config.mode


def _fail_closed(envelope: ActionEnvelope, rules: RuleResult | None) -> GuardrailDecision:
    if rules is not None and is_known_safe(rules):
        return GuardrailDecision.ALLOW
    if envelope.action.tool in RISKY_TOOLS:
        return GuardrailDecision.BLOCK
    if rules is not None and rules.disposition != RuleDisposition.PASS:
        return reduce_decision(rules, None)
    return GuardrailDecision.BLOCK


class Pipeline:
    def __init__(
        self,
        config: GuardrailConfig,
        *,
        laya: LayaClient | None = None,
        reviewer: object | None = None,
        sessions: SessionStore | None = None,
        traces: TraceWriter | None = None,
    ) -> None:
        self.config = config
        self.laya = laya or HttpLayaClient(
            base_url=config.laya.daemon_url,
            timeout=config.laya.timeout_seconds,
            model=config.laya.model,
            temperatures=config.laya.temperatures,
        )
        if reviewer is not None:
            self.reviewer = reviewer
        elif config.review.frontier_enabled:
            self.reviewer = ClaudeCliReviewer(timeout=config.review.timeout_seconds)
        else:
            self.reviewer = StubReviewer(unavailable=True)
        self.sessions = sessions or SessionStore()
        self.traces = traces or TraceWriter()

    def _frontier_skipped(self) -> bool:
        return self.config.mode == Mode.SHADOW and not self.config.review.run_in_shadow

    def evaluate(self, envelope: ActionEnvelope) -> EvaluationResult:
        error: str | None = None
        laya: LayaAssessment | None = None
        laya_error: str | None = None
        frontier_resp: ReviewResponse | None = None
        frontier_trace: FrontierTrace | None = None
        verification: VerificationDirective | None = None
        human_text: str | None = None
        policy = GuardrailDecision.ALLOW
        decision = GuardrailDecision.ALLOW
        rules = RuleResult(matched=[], disposition=RuleDisposition.PASS)
        try:
            envelope = apply_environment(envelope, self.config)
            rules = evaluate_rules(envelope, self.config)
            if rules.disposition == RuleDisposition.PASS:
                try:
                    state = build_laya_state(envelope, self.config)
                    laya = self.laya.assess(state)
                except LayaUnavailable as exc:
                    laya_error = str(exc)
                    if self.config.mode == Mode.SHADOW:
                        policy = GuardrailDecision.ALLOW
                    else:
                        policy = GuardrailDecision.FRONTIER_REVIEW
                else:
                    policy = reduce_decision(rules, laya, self.config.laya.thresholds)
            else:
                policy = reduce_decision(rules, laya, self.config.laya.thresholds)

            decision = policy
            frontier_skipped = False
            if decision == GuardrailDecision.FRONTIER_REVIEW:
                if not self.config.review.frontier_enabled:
                    decision = GuardrailDecision.HUMAN_APPROVAL
                elif self._frontier_skipped():
                    frontier_skipped = True
                    error = "frontier review skipped (shadow mode, review.run_in_shadow=false)"
                else:
                    try:
                        request = ReviewRequest(
                            goal=envelope.task.user_goal,
                            proposedAction=envelope.action,
                            environment=envelope.environment,
                            relevantContext=[
                                item.summary for item in envelope.context.recent_actions[-5:]
                            ],
                            matchedRules=list(rules.matched),
                            layaAssessment=laya,
                        )
                        frontier_resp = self.reviewer.review(request)
                        mapped = map_frontier(frontier_resp.decision)
                        if rules.disposition in {RuleDisposition.BLOCK, RuleDisposition.HUMAN}:
                            mapped = reduce_decision(rules, laya, self.config.laya.thresholds)
                        decision = mapped
                        frontier_trace = FrontierTrace(
                            model=self.config.review.model,
                            decision=frontier_resp.decision,
                            reason=frontier_resp.reason,
                        )
                    except (FrontierUnavailable, Exception) as exc:
                        error = str(exc)
                        decision = GuardrailDecision.HUMAN_APPROVAL

            key = action_key(
                envelope.action.command,
                envelope.action.target,
                envelope.action.tool,
                envelope.action.operation,
            )
            decision = apply_antiloop(
                session_id=envelope.session.id,
                store=self.sessions,
                key=key,
                decision=decision,
                max_verification=self.config.max_verification_cycles,
                max_replans=self.config.max_replans_per_action,
            )
            if (
                decision == GuardrailDecision.FRONTIER_REVIEW
                and frontier_resp is None
                and not frontier_skipped
            ):
                decision = GuardrailDecision.HUMAN_APPROVAL

            if decision == GuardrailDecision.ALLOW_WITH_VERIFICATION:
                verification = route_verification(envelope, laya)
            if decision == GuardrailDecision.HUMAN_APPROVAL:
                human_text = human_prompt(envelope, rules)
        except Exception as exc:
            error = str(exc)
            if self.config.mode == Mode.SHADOW:
                policy = GuardrailDecision.ALLOW
                decision = GuardrailDecision.ALLOW
            else:
                policy = _fail_closed(envelope, rules)
                decision = policy

        mode = effective_mode(self.config, rules, envelope)
        human = None
        if decision == GuardrailDecision.HUMAN_APPROVAL:
            human = HumanTrace(requested=True, decision=None)
        trace = self.traces.write(
            envelope=envelope,
            rules=rules,
            policy_decision=policy,
            final_decision=decision,
            mode=mode,
            laya=laya,
            laya_error=laya_error,
            frontier=frontier_trace,
            human=human,
            verification_skill=verification.skill if verification else None,
            error=error,
        )
        return EvaluationResult(
            envelope=envelope,
            rules=rules,
            decision=decision,
            policy_decision=policy,
            laya=laya,
            frontier=frontier_resp,
            verification=verification,
            human_prompt_text=human_text,
            trace=trace,
            error=error,
            mode=mode,
        )
