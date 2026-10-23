from lgh.schema.envelope import ActionEnvelope, InstructionContext
from lgh.schema.trace import ReviewContext
from lgh.state.redact import redact_text

MAX_SOURCE_CHARS = 8000


def build_review_context(envelope: ActionEnvelope) -> ReviewContext:
    truncated: list[str] = []

    def bounded(name: str, text: str | None, limit: int = MAX_SOURCE_CHARS) -> str | None:
        text = redact_text(text)
        if text is not None and len(text) > limit:
            truncated.append(name)
            return text[:limit - 1] + '…'
        return text

    context = envelope.task.instruction_context
    instructions = None
    if context is not None:
        instructions = InstructionContext(
            messages=[bounded('instructions', message, 4000) or '' for message in context.messages[-4:]],
            history_truncated=context.history_truncated or len(context.messages) > 4,
            text_truncated=context.text_truncated or 'instructions' in truncated,
        )
    return ReviewContext(
        goal=bounded('goal', envelope.task.user_goal) or '',
        instructions=instructions,
        command=bounded('command', envelope.action.command),
        plan=bounded('plan', envelope.task.current_plan),
        truncated_fields=truncated,
    )
