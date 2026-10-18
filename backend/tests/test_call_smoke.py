"""DB-free checks for the phone-bot smoke test helpers (scripts/call_smoke.py)."""
import importlib.util
import struct
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('call_smoke', Path(__file__).parents[1] / 'scripts/call_smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def wav(tag=7, channels=1, rate=8000, data=b'\x7f' * 400):
    fmt = struct.pack('<HHIIHH', tag, channels, rate, rate * channels, channels, 8)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', len(body)) + body


def test_wav_mulaw_payload_requires_8k_mono_mulaw():
    assert smoke.wav_mulaw_payload(wav()) == b'\x7f' * 400
    for bad in (wav(tag=1), wav(channels=2), wav(rate=16000)):
        with pytest.raises(ValueError):
            smoke.wav_mulaw_payload(bad)


def test_frames_are_20ms_and_padded_with_mulaw_silence():
    out = smoke.frames(b'\x01' * 330)
    assert [len(f) for f in out] == [160, 160, 160]
    assert out[-1] == b'\x01' * 10 + b'\xff' * 150
    assert smoke.frames(b'') == []
    assert len(smoke.silence(1.5)) == 12000


def speech(text, caller=False):
    data = {'text': text, 'audio_url': None}
    if caller:
        data.update(kind='caller', speaker='caller')
    return {'event': 'speech', 'data': data}


def tool(node_id, name, status='done'):
    return [{'event': 'node.create', 'data': {'node_id': node_id, 'type': 'forecast', 'title': 'Forecasting cash',
                                              'data': {'tool': name, 'args': {}}}},
            {'event': 'node.update', 'data': {'node_id': node_id, 'status': status, 'data': {'gap': 385} if status == 'done' else {'error': 'boom'}}}]


def bridge_run(second_tool_status='done'):
    # Production order: the books are read first, then the one question, then the owner's answer, then the re-forecast.
    return [
        {'event': 'run.start', 'data': {'run_id': 'r'}},
        {'event': 'node.create', 'data': {'node_id': 'context', 'type': 'context', 'title': 'Live phone call'}},
        speech('Hi, how can I help?'),
        speech('Am I going to make payroll these next two weeks?', caller=True),
        *tool('tool-1', 'forecast_cash'),
        speech('Should I assume Evergreen will pay by payday?'),
        speech('No.', caller=True),
        *tool('tool-2', 'forecast_cash', second_tool_status),
        speech('No, you are about $669 short. Would you like me to see who you can chase?'),  # an offer, not a clarification
        speech('What if Evergreen does pay?', caller=True),
        *tool('tool-3', 'forecast_cash'),
        speech('Then you would be covered.'),
        {'event': 'run.end', 'data': {'status': 'closed'}},
    ]


def test_assess_reads_the_bridge_run():
    a = smoke.assess(bridge_run())
    assert a['greeting'] == 'Hi, how can I help?'
    assert a['caller_turns'] == ['Am I going to make payroll these next two weeks?', 'No.', 'What if Evergreen does pay?']
    assert a['tool_calls'] == ['forecast_cash', 'forecast_cash', 'forecast_cash'] and a['failed_tools'] == []
    assert a['clarifying_questions'] == ['Should I assume Evergreen will pay by payday?']
    # the spoken answer is what came back after the owner answered the question, not the question itself
    assert a['spoken_answer'] == 'No, you are about $669 short. Would you like me to see who you can chase?'
    assert a['followup_answer'] == 'Then you would be covered.'
    assert a['failed'] is None and a['ended'] == 'closed'
    assert a['checks'] == {'greeting': True, 'transcribed_question': True, 'tool_calls': True, 'no_failed_tools': True,
                           'spoken_answer': True, 'one_clarifying_question': True, 'followup_answered': True}


def test_assess_fails_when_a_tool_failed_even_if_the_bot_kept_talking():
    a = smoke.assess(bridge_run(second_tool_status='failed'))
    assert a['failed_tools'] == ['forecast_cash'] and a['checks']['no_failed_tools'] is False
    assert a['tool_calls'] == ['forecast_cash', 'forecast_cash']  # only completed calls count


def test_assess_reports_a_rejected_live_session():
    events = [{'event': 'node.create', 'data': {'node_id': 'context', 'type': 'context', 'title': 'Live phone call'}},
              {'event': 'node.update', 'data': {'node_id': 'context', 'status': 'failed',
                                                'data': {'error': 'Voice session disconnected'}}},
              {'event': 'run.end', 'data': {'status': 'closed'}}]
    a = smoke.assess(events)
    assert a['failed'] == 'Voice session disconnected' and a['greeting'] is None
    assert not any(v for k, v in a['checks'].items() if k != 'no_failed_tools')  # nothing ran, so nothing failed


def test_lone_question_is_one_question_and_nothing_else():
    assert smoke.is_lone_question('Should I assume Evergreen will pay by October 20, or treat them as not paying?')
    assert not smoke.is_lone_question("You'll be $669 short. Would you like me to see who you can chase?")
    assert not smoke.is_lone_question('No, you are short.')
