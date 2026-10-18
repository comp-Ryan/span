import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from owed.voice import live
from owed.voice.live import (
    Playback, SpokenTranscript, live_system_instruction, persist_first_caller_question,
    respond_to_tool_calls,
)


def test_barge_in_cancels_audio_and_clears_queued_speech():
    async def check():
        ws = AsyncMock()
        playback = Playback(ws, 'stream-test')
        playback.current = asyncio.create_task(asyncio.sleep(30))
        await playback.queue.put('stale speech')
        await playback.interrupt()
        assert playback.current.cancelled()
        assert playback.queue.empty()
        ws.send_json.assert_awaited_once_with({'event': 'clear', 'streamSid': 'stream-test'})
    asyncio.run(check())


def test_playback_worker_continues_after_tts_failure(monkeypatch):
    async def check():
        ws = AsyncMock()
        playback = Playback(ws, 'stream-test')
        requested = []

        async def fake_tts_chunks(text):
            requested.append(text)
            if text == 'fails':
                raise RuntimeError('TTS unavailable')
            yield b'audio'

        monkeypatch.setattr(live, 'tts_chunks', fake_tts_chunks)
        worker = asyncio.create_task(playback.worker())
        await playback.queue.put('fails')
        await playback.queue.put('succeeds')

        await asyncio.wait_for(playback.queue.join(), timeout=1)

        assert not worker.done()
        assert requested == ['fails', 'succeeds']
        ws.send_json.assert_awaited_once()
        assert ws.send_json.await_args.args[0]['event'] == 'media'

        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('worker cancellation should propagate')
        assert worker.cancelled()

    asyncio.run(check())


def test_report_delimiter_is_filtered_even_when_split_across_chunks():
    transcript = SpokenTranscript()
    assert transcript.feed('A short answer --') == 'A short answer '
    assert transcript.feed('- Written report') == ''
    assert transcript.finish() == ''


def test_partial_delimiter_prefix_is_flushed_when_turn_ends():
    transcript = SpokenTranscript()
    assert transcript.feed('A short answer -') == 'A short answer '
    assert transcript.finish() == '-'


def test_live_instruction_excludes_planner_written_report_contract():
    instruction = live_system_instruction('Example Co', '2026-10-09')
    assert 'Example Co' in instruction
    assert 'Ask exactly one clarifying question' in instruction
    assert 'latest correction replaces the earlier assumption' in instruction
    assert 'written report for the owner' not in instruction
    assert 'Reply in two parts' not in instruction


def test_multiple_live_actions_only_execute_first_until_owner_answers():
    async def check():
        ctx = SimpleNamespace(execute=AsyncMock(return_value={
            'status': 'approval_required', 'decision_id': 'decision-1'}))
        session = SimpleNamespace(send_tool_response=AsyncMock())
        calls = [
            SimpleNamespace(id='call-1', name='send_message', args={'invoice_id': 'inv-1'}),
            SimpleNamespace(id='call-2', name='defer_bill', args={'bill_id': 'bill-1'}),
        ]

        await respond_to_tool_calls(ctx, session, calls)

        ctx.execute.assert_awaited_once_with('send_message', {'invoice_id': 'inv-1'})
        responses = session.send_tool_response.await_args.kwargs['function_responses']
        assert [response.id for response in responses] == ['call-1', 'call-2']
        assert responses[1].response['status'] == 'waiting_for_owner'

    asyncio.run(check())


def test_live_call_waits_after_resolving_an_action_before_proposing_another():
    async def check():
        ctx = SimpleNamespace(execute=AsyncMock(return_value={'resolved': 'yes'}))
        session = SimpleNamespace(send_tool_response=AsyncMock())
        calls = [
            SimpleNamespace(id='call-1', name='resolve_decision', args={'decision_id': 'd-1', 'option_id': 'yes'}),
            SimpleNamespace(id='call-2', name='send_message', args={'invoice_id': 'inv-2'}),
        ]

        await respond_to_tool_calls(ctx, session, calls)

        ctx.execute.assert_awaited_once_with('resolve_decision', {'decision_id': 'd-1', 'option_id': 'yes'})
        responses = session.send_tool_response.await_args.kwargs['function_responses']
        assert responses[1].response['status'] == 'waiting_for_owner'

    asyncio.run(check())


def test_first_caller_question_is_normalized_bounded_and_only_replaces_placeholder(monkeypatch):
    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, query, params):
            self.calls.append((query, params))
            return SimpleNamespace(rowcount=1)

    class ConnectionContext:
        def __enter__(self):
            return connection

        def __exit__(self, *_args):
            return None

    connection = Connection()
    manager = ConnectionContext()
    monkeypatch.setattr(live, 'conn', lambda: manager)
    text = '  What   is the cash position?  ' + ('x' * 4100)

    assert persist_first_caller_question('run-call', text) is True

    # This DB-free check asserts both the 4000-character cap and the conditional
    # placeholder predicate, which prevents later caller turns overwriting it.
    query, params = connection.calls[0]
    assert 'and question=%s' in query
    assert params[0].startswith('What is the cash position? x')
    assert len(params[0]) == 4000
    assert params[1:] == ('run-call', 'Live phone call')

    connection.calls.clear()
    assert persist_first_caller_question('run-call', ' \n\t ') is False
    assert connection.calls == []


def test_settings_accept_the_eleven_labs_key_alias_and_default_voice(monkeypatch):
    from owed.config import Settings
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    monkeypatch.delenv('ELEVENLABS_VOICE_ID', raising=False)
    monkeypatch.setenv('ELEVEN_LABS_KEY', 'alias-key')
    s = Settings(_env_file=None)
    assert s.elevenlabs_api_key == 'alias-key'
    assert s.elevenlabs_voice_id  # a premade ElevenLabs voice so the bridge speaks without extra config


def test_browser_voice_speech_endpoint_streams_elevenlabs_or_says_so(monkeypatch):
    from fastapi.testclient import TestClient
    from owed.config import settings
    from owed.main import app
    client = TestClient(app)
    monkeypatch.setattr(settings, 'elevenlabs_api_key', '')
    assert client.get('/api/voice/speech', params={'text': 'hello'}).status_code == 503
    monkeypatch.setattr(settings, 'elevenlabs_api_key', 'k')

    async def fake_mp3(text):
        assert text == 'You are short by $385.'
        yield b'ID3'
        yield b'rest'
    monkeypatch.setattr(live, 'tts_mp3', fake_mp3)
    r = client.get('/api/voice/speech', params={'text': 'You are short by $385.'})
    assert r.status_code == 200 and r.headers['content-type'].startswith('audio/mpeg') and r.content == b'ID3rest'
    assert client.get('/api/voice/speech', params={'text': ''}).status_code == 422
    assert client.get('/api/voice/speech', params={'text': 'x' * 2001}).status_code == 422


def test_health_reports_voice_readiness(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from owed import db
    from owed.config import settings
    from owed.main import app
    monkeypatch.setattr(db, 'conn', lambda: nullcontext(SimpleNamespace(execute=lambda *a: None)))
    monkeypatch.setattr(settings, 'gemini_api_key', 'g')
    monkeypatch.setattr(settings, 'twilio_auth_token', '')
    monkeypatch.setattr(settings, 'voice_stream_token', '')
    monkeypatch.setattr(settings, 'elevenlabs_api_key', 'k')
    monkeypatch.setattr(settings, 'voice_phone_number', '')
    voice = TestClient(app).get('/api/health').json()['voice']
    assert voice == {'browser': True, 'phone': False, 'phone_number': None, 'elevenlabs': True, 'live_model': settings.gemini_live_model}
    monkeypatch.setattr(settings, 'twilio_auth_token', 't')
    monkeypatch.setattr(settings, 'voice_stream_token', 's')
    monkeypatch.setattr(settings, 'voice_phone_number', '+1 555 010 0000')
    assert TestClient(app).get('/api/health').json()['voice']['phone'] is True
