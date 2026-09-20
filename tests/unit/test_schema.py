from lgh.schema.decision import GuardrailDecision
from lgh.schema.envelope import ActionEnvelope
from tests.helpers import make_envelope


def test_envelope_roundtrip() -> None:
    env = make_envelope(command="pytest", goal="run tests")
    dumped = env.model_dump(by_alias=True)
    again = ActionEnvelope.model_validate(dumped)
    assert again.task.user_goal == "run tests"
    assert again.schema_version == "0.1"


def test_decision_values() -> None:
    assert GuardrailDecision.ALLOW == "ALLOW"
    assert len(GuardrailDecision) == 6
