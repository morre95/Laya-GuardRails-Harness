import json

from lgh.adapters.claude_code.transcript import last_user_goal, read_instruction_context


def _transcript(tmp_path, records):
    path = tmp_path / 'transcript.jsonl'
    path.write_text('\n'.join(json.dumps(row) for row in records), encoding='utf-8')
    return str(path)


def test_tool_results_never_replace_user_instruction(tmp_path):
    path = _transcript(tmp_path, [
        {'type': 'user', 'message': {'role': 'user', 'content': 'Fix the web server'}},
        {'type': 'user', 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': 'tool-1', 'content': 'AGENTS.md\nREADME.md'},
        ]}},
    ])
    assert last_user_goal(path) == 'Fix the web server'
    assert read_instruction_context(path).messages == ['Fix the web server']


def test_mixed_blocks_only_extract_user_text(tmp_path):
    path = _transcript(tmp_path, [{'type': 'user', 'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'content': 'do not treat this as a goal'},
        {'type': 'text', 'text': 'Also add tests\nKeep the public API'},
        {'type': 'image', 'source': {'data': 'not text'}},
    ]}}])
    assert read_instruction_context(path).messages == ['Also add tests\nKeep the public API']


def test_followup_keeps_prior_request_and_excludes_system_context(tmp_path):
    path = _transcript(tmp_path, [
        {'role': 'user', 'content': 'Fix the web server'},
        {'type': 'assistant', 'message': {'role': 'assistant', 'content': 'I will read the routes'}},
        {'type': 'user', 'isMeta': True, 'message': {'role': 'user', 'content': 'system reminder'}},
        {'type': 'user', 'isCompactSummary': True, 'message': {'role': 'user', 'content': 'generated summary'}},
        {'role': 'human', 'content': 'Yes, continue'},
    ])
    context = read_instruction_context(path)
    assert context.messages == ['Fix the web server', 'Yes, continue']
    goal = last_user_goal(path)
    assert 'Fix the web server' in goal and 'Yes, continue' in goal
    assert goal.index('Fix the web server') < goal.index('Yes, continue')


def test_context_is_bounded_redacted_and_reports_truncation(tmp_path):
    path = _transcript(tmp_path, [
        {'role': 'user', 'content': f'Instruction {i} ' + 'x' * 5000 + ' token=secret-value'}
        for i in range(6)
    ])
    context = read_instruction_context(path)
    assert len(context.messages) == 4
    assert context.history_truncated and context.text_truncated
    assert all(len(text) <= 4000 for text in context.messages)
    assert 'secret-value' not in context.model_dump_json()
    assert len(last_user_goal(path)) <= 400


def test_malformed_records_do_not_crash_or_turn_objects_into_text(tmp_path):
    path = _transcript(tmp_path, [None, [], 'text', {'role': 'user', 'content': {'content': [
        {'type': 'tool_result', 'content': 'files'}]}}, {'role': 'user', 'content': 'Actual request'}])
    assert last_user_goal(path) == 'Actual request'


def test_no_transcript_has_explicit_empty_context(tmp_path):
    assert read_instruction_context(None).messages == []
    assert last_user_goal(str(tmp_path / 'missing')) == ''


def test_large_transcript_reports_missing_earlier_history(tmp_path):
    path = tmp_path / 'large.jsonl'
    path.write_text(json.dumps({'role': 'user', 'content': 'Old request'}) + '\n'
                    + json.dumps({'role': 'assistant', 'content': 'x' * 520000}) + '\n'
                    + json.dumps({'role': 'user', 'content': 'Latest clarification'}) + '\n')
    context = read_instruction_context(str(path))
    assert context.messages == ['Latest clarification']
    assert context.history_truncated


def test_invalid_role_and_block_type_are_ignored(tmp_path):
    path = _transcript(tmp_path, [
        {'role': [], 'content': 'Invalid role'},
        {'role': 'user', 'content': {'type': {}, 'text': 'Invalid block'}},
        {'role': 'user', 'content': 'Keep this request'},
    ])
    assert last_user_goal(path) == 'Keep this request'
