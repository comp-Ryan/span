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


def test_assess_reads_the_bridge_run():
    events = [
        {'event': 'run.start', 'data': {'run_id': 'r'}},
        {'event': 'node.create', 'data': {'node_id': 'context', 'type': 'context', 'title': 'Live phone call'}},
        speech('Hi, how can I help?'),
        speech('Am I going to make payroll these next two weeks?', caller=True),
        speech('Should I assume Evergreen will pay by payday?'),
        speech('No.', caller=True),
        {'event': 'node.create', 'data': {'node_id': 'tool-1', 'type': 'forecast', 'title': 'Forecasting cash',
                                          'data': {'tool': 'forecast_cash', 'args': {}}}},
        {'event': 'node.update', 'data': {'node_id': 'tool-1', 'status': 'done', 'data': {'gap': 385}}},
        speech('No, you are about $385 short.'),
        speech('What if Evergreen does pay?', caller=True),
        {'event': 'node.create', 'data': {'node_id': 'tool-2', 'type': 'forecast', 'title': 'Forecasting cash',
                                          'data': {'tool': 'forecast_cash', 'args': {'will_pay': True}}}},
        speech('Then you would be covered.'),
        {'event': 'run.end', 'data': {'status': 'closed'}},
    ]
    a = smoke.assess(events)
    assert a['greeting'] == 'Hi, how can I help?'
    assert a['caller_turns'] == ['Am I going to make payroll these next two weeks?', 'No.', 'What if Evergreen does pay?']
    assert a['tool_calls'] == ['forecast_cash', 'forecast_cash']
    assert a['clarifying_questions'] == ['Should I assume Evergreen will pay by payday?']
    assert a['spoken_answer'] == 'No, you are about $385 short.'
    assert a['followup_answer'] == 'Then you would be covered.'
    assert a['failed'] is None and a['ended'] == 'closed'
    assert a['checks'] == {'greeting': True, 'transcribed_question': True, 'tool_calls': True, 'spoken_answer': True,
                           'one_clarifying_question': True, 'followup_answered': True}


def test_assess_reports_a_rejected_live_session():
    events = [{'event': 'node.create', 'data': {'node_id': 'context', 'type': 'context', 'title': 'Live phone call'}},
              {'event': 'node.update', 'data': {'node_id': 'context', 'status': 'failed',
                                                'data': {'error': 'Voice session disconnected'}}},
              {'event': 'run.end', 'data': {'status': 'closed'}}]
    a = smoke.assess(events)
    assert a['failed'] == 'Voice session disconnected' and a['greeting'] is None
    assert not any(a['checks'].values())
