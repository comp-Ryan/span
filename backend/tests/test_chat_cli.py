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


def test_run_is_settled_only_by_run_end_so_the_answer_prints_before_any_prompt():
    assert chat.settled([{'event': 'run.end', 'data': {'status': 'closed'}}]) == 'closed'
    # the planner emits the approval before its spoken answer: a pending decision alone is not the end
    assert chat.settled([{'event': 'decision', 'data': {'decision_id': 'd1', 'options': OPTIONS}}]) is None
    assert chat.settled([{'event': 'speech', 'data': {'text': 'hi'}}]) is None


def test_render_uses_node_titles_when_it_knows_them():
    titles = {'tool-1': 'Forecasting cash to Oct 24'}
    done = {'event': 'node.update', 'data': {'node_id': 'tool-1', 'status': 'done', 'data': {'summary': '$385 short'}}}
    assert chat.render(done, titles) == '  ✓ Forecasting cash to Oct 24 · $385 short'
    assert chat.render(done) == '  ✓ tool-1 · $385 short'


class FakeServer:
    """Replays a run's events in slices, like polling a backend that is still working."""
    def __init__(self, slices):
        self.slices, self.calls, self.resolved = slices, 0, []

    def events(self, run_id):
        self.calls += 1
        return self.slices[min(self.calls, len(self.slices)) - 1]

    def resolve(self, decision_id, option):
        self.resolved.append((decision_id, option))


def test_follow_prints_the_answer_before_prompting_and_then_only_watches_new_events(monkeypatch):
    import io
    monkeypatch.setattr(chat.time, 'sleep', lambda s: None)
    decision = {'event': 'decision', 'data': {'decision_id': 'd1', 'prompt': 'Text them?', 'options': OPTIONS}}
    answer = {'event': 'speech', 'data': {'text': 'Chase three late payers.'}}
    first_end = {'event': 'run.end', 'data': {'status': 'open'}}
    after = [{'event': 'node.create', 'data': {'node_id': 'msg-1', 'type': 'message', 'title': 'Texted Hearth Trading', 'status': 'running'}}, {'event': 'run.end', 'data': {'status': 'closed'}}]
    server = FakeServer([[decision], [decision, answer], [decision, answer, first_end], [decision, answer, first_end] + after])
    out = io.StringIO()
    c = chat.Chat('http://x', 'company-020', out=out)
    monkeypatch.setattr(c, 'events', server.events)
    monkeypatch.setattr(c, 'resolve', server.resolve)
    seen = chat.Seen()
    state, events = c.follow('run-1', seen)
    assert state == 'open' and server.calls == 3
    assert out.getvalue().index('Chase three late payers.') > out.getvalue().index('Text them?')
    state, events = c.follow('run-1', seen)  # after the owner decides: the earlier run.end must not end this wait
    assert state == 'closed' and server.calls == 4 and 'Texted Hearth Trading' in out.getvalue()


def test_after_a_decision_the_wait_ends_when_events_go_quiet_even_without_a_new_run_end(monkeypatch):
    import io
    clock = {'t': 0.0}
    monkeypatch.setattr(chat.time, 'time', lambda: clock['t'])
    monkeypatch.setattr(chat.time, 'sleep', lambda s: clock.__setitem__('t', clock['t'] + s))
    first_end = {'event': 'run.end', 'data': {'status': 'closed'}}  # the planner closed the run before the owner answered
    resolved = {'event': 'decision.resolved', 'data': {'decision_id': 'd1', 'option_id': 'no'}}
    server = FakeServer([[first_end], [first_end, resolved], [first_end, resolved]])
    c = chat.Chat('http://x', 'company-020', out=io.StringIO())
    monkeypatch.setattr(c, 'events', server.events)
    seen = chat.Seen(); c.follow('run-1', seen)
    state, _ = c.follow('run-1', seen, timeout=240, quiet=20.0, need_speech=False)
    assert state == 'quiet' and clock['t'] < 60
