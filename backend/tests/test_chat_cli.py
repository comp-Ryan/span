"""scripts/chat.py: a terminal chat with Span for local testing (no browser, no voice)."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'chat.py'
spec = importlib.util.spec_from_file_location('span_chat_cli', SCRIPT)
chat = importlib.util.module_from_spec(spec)
sys.modules['span_chat_cli'] = chat
spec.loader.exec_module(chat)

OPTIONS = [{'id': 'yes', 'label': 'Yes, text them'}, {'id': 'chase_only', 'label': "Text, don't touch bills"}, {'id': 'no', 'label': 'Not now'}]


def test_choose_option_accepts_ids_numbers_and_plain_words():
    assert chat.choose_option('yes', OPTIONS) == 'yes'
    assert chat.choose_option('Y', OPTIONS) == 'yes'
    assert chat.choose_option('yeah do it', OPTIONS) == 'yes'
    assert chat.choose_option('n', OPTIONS) == 'no'
    assert chat.choose_option('no thanks', OPTIONS) == 'no'
    assert chat.choose_option('2', OPTIONS) == 'chase_only'
    assert chat.choose_option("text, don't touch bills", OPTIONS) == 'chase_only'
    assert chat.choose_option('chase_only', OPTIONS) == 'chase_only'
    assert chat.choose_option('maybe later', OPTIONS) is None
    assert chat.choose_option('', OPTIONS) is None


def test_render_turns_events_into_terminal_lines():
    lines = [chat.render(e) for e in [
        {'event': 'run.start', 'data': {'run_id': 'run-1', 'question': 'Will I make payroll?'}},
        {'event': 'node.create', 'data': {'node_id': 'tool-1', 'type': 'tool', 'title': 'Forecasting cash to Oct 24', 'status': 'running'}},
        {'event': 'node.update', 'data': {'node_id': 'tool-1', 'status': 'done', 'data': {'summary': '$385 short'}}},
        {'event': 'node.update', 'data': {'node_id': 'tool-2', 'status': 'failed', 'data': {'error': 'boom'}}},
        {'event': 'speech', 'data': {'text': 'No. You are $385 short.'}},
        {'event': 'decision', 'data': {'decision_id': 'd1', 'prompt': 'Text them?', 'options': OPTIONS}},
        {'event': 'decision.resolved', 'data': {'decision_id': 'd1', 'option_id': 'yes'}},
        {'event': 'run.end', 'data': {'status': 'open'}},
        {'event': 'node.progress', 'data': {'node_id': 'x'}},
    ]]
    assert lines[0] == '[run-1] Will I make payroll?'
    assert lines[1] == '  … Forecasting cash to Oct 24'
    assert lines[2] == '  ✓ tool-1 · $385 short'
    assert lines[3] == '  ✗ tool-2 · boom'
    assert lines[4] == 'span> No. You are $385 short.'
    assert lines[5] == "span> Text them?\n  [1] yes · Yes, text them\n  [2] chase_only · Text, don't touch bills\n  [3] no · Not now"
    assert lines[6] == '  decided: yes'
    assert lines[7] == '  — run open —'
    assert lines[8] is None


def test_new_events_only_yields_what_was_not_printed_yet():
    seen = chat.Seen()
    first = [{'event': 'run.start', 'data': {}}, {'event': 'speech', 'data': {'text': 'a'}}]
    assert seen.take(first) == first
    assert seen.take(first) == []
    later = first + [{'event': 'run.end', 'data': {'status': 'closed'}}]
    assert seen.take(later) == [later[2]]


def test_pending_decision_is_the_last_unresolved_one():
    events = [
        {'event': 'decision', 'data': {'decision_id': 'd1', 'prompt': 'Text them?', 'options': OPTIONS}},
        {'event': 'decision.resolved', 'data': {'decision_id': 'd1', 'option_id': 'no'}},
        {'event': 'decision', 'data': {'decision_id': 'd2', 'prompt': 'Defer the bill?', 'options': OPTIONS}},
    ]
    assert chat.pending_decision(events)['decision_id'] == 'd2'
    assert chat.pending_decision(events[:2]) is None


def test_run_is_settled_when_ended_or_waiting_on_the_owner():
    assert chat.settled([{'event': 'run.end', 'data': {'status': 'closed'}}]) == 'closed'
    assert chat.settled([{'event': 'decision', 'data': {'decision_id': 'd1', 'options': OPTIONS}}]) == 'decision'
    assert chat.settled([{'event': 'speech', 'data': {'text': 'hi'}}]) is None
