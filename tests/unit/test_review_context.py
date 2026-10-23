from lgh.schema.envelope import InstructionContext
from lgh.state.builder import build_laya_state
from lgh.trace.writer import build_trace
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.rules import RuleDisposition, RuleResult
from tests.helpers import make_envelope


def test_review_context_is_redacted_and_does_not_replace_model_input():
    command = 'printf hello\n' + 'x' * 1500 + '\ntoken=super-secret'
    env = make_envelope(command=command, goal='Fix routes')
    task = env.task.model_copy(update={'instruction_context': InstructionContext(
        messages=['Fix routes', 'Keep the API\npassword=hidden-value'])})
    env = env.model_copy(update={'task': task})
    state = build_laya_state(env)
    trace = build_trace(envelope=env, rules=RuleResult(matched=[], disposition=RuleDisposition.PASS),
                        policy_decision=GuardrailDecision.ALLOW, final_decision=GuardrailDecision.ALLOW,
                        mode=Mode.SHADOW, state=state)
    assert trace.state == state
    assert trace.review_context.command.startswith('printf hello\n')
    assert len(trace.review_context.command) > len(state.action.command)
    assert trace.review_context.instructions.messages == ['Fix routes', 'Keep the API\n[REDACTED]']
    assert 'super-secret' not in trace.model_dump_json()
    assert 'hidden-value' not in trace.model_dump_json()


def test_review_command_is_bounded_and_reports_truncation():
    env = make_envelope(command='x' * 9000)
    trace = build_trace(envelope=env, rules=RuleResult(matched=[], disposition=RuleDisposition.PASS),
                        policy_decision=GuardrailDecision.ALLOW, final_decision=GuardrailDecision.ALLOW,
                        mode=Mode.SHADOW)
    assert len(trace.review_context.command) == 8000
    assert 'command' in trace.review_context.truncated_fields
