"""Twilio Media Streams fallback; Photon currently publishes SIP, not WS media."""
import asyncio
import audioop
import base64
import contextlib
import hashlib
import hmac
import logging
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from google import genai
from google.genai import types

from owed.config import settings
from owed.db import conn
from owed.events import emit
from owed.planner import TOOLS, ToolContext, system_prompt
from owed.runs import create, finish
from owed.runs.payroll import target_for

router = APIRouter()
log = logging.getLogger(__name__)
LIVE_CALL_PLACEHOLDER = 'Live phone call'
RUN_QUESTION_LIMIT = 4000


def persist_first_caller_question(run_id, text):
    """Replace the live-call placeholder once, keeping the runs question bounded."""
    question = ' '.join((text or '').split())[:RUN_QUESTION_LIMIT]
    if not question:
        return False
    with conn() as c:
        result = c.execute(
            'update runs set question=%s where run_id=%s and question=%s',
            (question, run_id, LIVE_CALL_PLACEHOLDER),
        )
    return result.rowcount == 1

VOICE_INSTRUCTIONS = """\
You are speaking live on a phone call. Speak only in short, natural, plain spoken turns.
Never use Markdown, headings, lists, a written report, or a report delimiter. The caller must
hear only what you would say aloud. Ask exactly one clarifying question at a time, then stop
and wait for the caller's answer before continuing or using the answer. If the caller corrects
or redoes an answer, the latest correction replaces the earlier assumption; redo only that step.
When the caller gives an explicit forecast horizon (such as "the next two weeks"), calculate
the end date from the dataset clock in your instructions and pass that exact ISO date as
forecast_cash.target_date. Do not silently replace an explicit horizon with next Friday.
When forecast_cash returns assumption_needed, ask exactly its question and wait for the answer;
then call forecast_cash again with that customer_id and will_pay set to the answer. Handle only
one owner approval or action at a time and wait for the owner's explicit answer before proposing
another.
Begin by asking how you can help."""


def live_system_instruction(company, target):
    """Keep planner grounding, but deliberately exclude its written-report contract."""
    prompt = system_prompt(company, target)
    prompt = prompt.split('\nReply in two parts separated by a line containing only ---', 1)[0]
    return f'{prompt}\n{VOICE_INSTRUCTIONS}'


class SpokenTranscript:
    """Incrementally pass only speech before a planner report delimiter."""

    delimiter = '---'

    def __init__(self):
        self.buffer = ''
        self.in_report = False

    def feed(self, chunk):
        if self.in_report:
            return ''
        text = self.buffer + chunk
        delimiter_at = text.find(self.delimiter)
        if delimiter_at >= 0:
            self.in_report = True
            self.buffer = ''
            return text[:delimiter_at]
        # Hold a possible delimiter prefix so a marker split over chunks cannot leak.
        keep = 0
        for size in range(1, len(self.delimiter)):
            if text.endswith(self.delimiter[:size]):
                keep = size
        if keep:
            self.buffer = text[-keep:]
            return text[:-keep]
        self.buffer = ''
        return text

    def finish(self):
        if self.in_report:
            self.buffer = ''
            return ''
        text, self.buffer = self.buffer, ''
        return text


ACTION_TOOLS = {'send_message', 'defer_bill', 'rank_chase', 'resolve_decision'}


async def respond_to_tool_calls(ctx, session, calls):
    """Execute calls serially and do not run a second tool after an owner action."""
    responses = []
    owner_action_requested = False
    for call in calls:
        if owner_action_requested:
            result = {'status': 'waiting_for_owner',
                      'message': 'Wait for the owner to answer the pending action before continuing.'}
        else:
            result = await ctx.execute(call.name, call.args or {})
            if call.name in ACTION_TOOLS:
                owner_action_requested = True
        responses.append(types.FunctionResponse(
            id=call.id, name=call.name, response=result))
    if responses:
        # The Live SDK accepts a sequence of FunctionResponse objects for one tool-call event.
        await session.send_tool_response(function_responses=responses)


async def tts_chunks(text):
    async with (
        httpx.AsyncClient(timeout=30) as client,
        client.stream(
            'POST',
            f'https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}/stream',
            params={'output_format': 'ulaw_8000'},
            headers={'xi-api-key': settings.elevenlabs_api_key},
            json={'text': text, 'model_id': 'eleven_flash_v2_5'},
        ) as response,
    ):
        response.raise_for_status()
        async for chunk in response.aiter_bytes(160):
            if chunk:
                yield chunk


class Playback:
    def __init__(self, ws, stream_id):
        self.ws, self.stream_id = ws, stream_id
        self.queue = asyncio.Queue(maxsize=100)
        self.current = None

    async def media(self, chunk):
        await self.ws.send_json({'event': 'media', 'streamSid': self.stream_id,
                                 'media': {'payload': base64.b64encode(chunk).decode()}})

    async def speak(self, text):
        async for chunk in tts_chunks(text):
            await self.media(chunk)
            await asyncio.sleep(len(chunk) / 8000)  # avoid overflowing carrier playback buffers

    async def worker(self):
        while True:
            text = await self.queue.get()
            self.current = asyncio.create_task(self.speak(text))
            try:
                await self.current
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
            except Exception:
                log.exception('Live call TTS failed while playing an utterance')
            finally:
                self.current = None
                self.queue.task_done()

    async def interrupt(self):
        if self.current:
            self.current.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.current
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        await self.ws.send_json({'event': 'clear', 'streamSid': self.stream_id})


@router.post('/voice/twiml')
async def twiml(request: Request):
    if not settings.twilio_auth_token or not settings.voice_stream_token:
        raise HTTPException(503, 'Voice credentials are not configured')
    form = parse_qs((await request.body()).decode())
    url = settings.public_base_url.rstrip('/') + str(request.url.path)
    if request.url.query:
        url += '?' + request.url.query
    signed = url + ''.join(k + v for k in sorted(form) for v in sorted(set(form[k])))
    expected = base64.b64encode(hmac.new(settings.twilio_auth_token.encode(), signed.encode(), hashlib.sha1).digest()).decode()
    if not hmac.compare_digest(expected, request.headers.get('x-twilio-signature', '')):
        raise HTTPException(403, 'Invalid call signature')
    ws_url = settings.public_base_url.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/') + '/voice/photon'
    xml = f'<Response><Connect><Stream url="{escape(ws_url)}"><Parameter name="token" value="{escape(settings.voice_stream_token)}"/><Parameter name="company" value="{escape(settings.demo_company)}"/></Stream></Connect></Response>'
    return Response(xml, media_type='application/xml')


@router.websocket('/voice/photon')
async def live_call(ws: WebSocket):
    await ws.accept()
    if not settings.gemini_api_key or not settings.voice_stream_token:
        await ws.close(code=1013, reason='Voice is not configured')
        return
    run_id, client, tasks, playback = None, None, [], None
    try:
        async with asyncio.timeout(10):
            start = await ws.receive_json()
            if start.get('event') == 'connected':
                start = await ws.receive_json()
        if start.get('event') != 'start':
            await ws.close(code=1008, reason='Expected stream start')
            return
        meta = start['start']
        params = meta.get('customParameters', {})
        if not hmac.compare_digest(str(params.get('token', '')), settings.voice_stream_token):
            await ws.close(code=1008, reason='Invalid stream token')
            return
        fmt = meta.get('mediaFormat', {})
        if fmt.get('encoding') != 'audio/x-mulaw' or fmt.get('sampleRate') != 8000 or fmt.get('channels') != 1:
            await ws.close(code=1003, reason='Expected mono mulaw 8kHz')
            return
        company = params.get('company', settings.demo_company)
        run_id = await asyncio.to_thread(create, company, LIVE_CALL_PLACEHOLDER, 'call', 'free_question')
        await asyncio.to_thread(emit, run_id, 'node.create', {'node_id': 'context', 'type': 'context',
            'title': 'Live phone call', 'status': 'running', 'parent': None})
        ctx = ToolContext(run_id, company, target_for('Friday'))
        playback = Playback(ws, meta['streamSid'])
        client = genai.Client(api_key=settings.gemini_api_key)
        use_eleven = bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)
        config = {'response_modalities': ['AUDIO'], 'input_audio_transcription': {},
                  'output_audio_transcription': {}, 'tools': [{'function_declarations': TOOLS}],
                  'system_instruction': live_system_instruction(company, ctx.target)}
        async with client.aio.live.connect(model=settings.gemini_live_model, config=config) as session:
            async def receive_caller():
                state = None
                while True:
                    message = await ws.receive_json()
                    if message.get('event') == 'stop':
                        return
                    if message.get('event') == 'media':
                        pcm = audioop.ulaw2lin(base64.b64decode(message['media']['payload'], validate=True), 2)
                        pcm, state = audioop.ratecv(pcm, 2, 1, 8000, 16000, state)
                        await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type='audio/pcm;rate=16000'))

            async def receive_gemini():
                pending_text, spoken_text, audio_state = '', '', None
                caller_question_saved = False
                transcript = SpokenTranscript()
                while True:
                    async for response in session.receive():
                        content = response.server_content
                        if content:
                            if content.interrupted:
                                pending_text = ''
                                spoken_text = ''
                                transcript = SpokenTranscript()
                                await playback.interrupt()
                            if content.input_transcription and content.input_transcription.text:
                                caller_text = content.input_transcription.text.strip()
                                if caller_text:
                                    if not caller_question_saved:
                                        await asyncio.to_thread(persist_first_caller_question, run_id, caller_text)
                                        caller_question_saved = True
                                    await asyncio.to_thread(emit, run_id, 'speech', {
                                        'kind': 'caller', 'speaker': 'caller', 'text': caller_text,
                                        'audio_url': None,
                                    })
                                await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': 'context',
                                    'data': {'caller_text': caller_text}})
                            if content.output_transcription and content.output_transcription.text:
                                text = transcript.feed(content.output_transcription.text)
                                if text:
                                    pending_text += text
                                    spoken_text += text
                                    if use_eleven and (pending_text.rstrip().endswith(('.', '?', '!')) or len(pending_text) > 180):
                                        await playback.queue.put(pending_text)
                                        pending_text = ''
                            if not use_eleven and content.model_turn:
                                # Inline audio cannot be retracted after streaming; the voice-only
                                # instruction above is the protection for this audio path.
                                for part in content.model_turn.parts or []:
                                    if part.inline_data:
                                        pcm, audio_state = audioop.ratecv(part.inline_data.data, 2, 1, 24000, 8000, audio_state)
                                        await playback.media(audioop.lin2ulaw(pcm, 2))
                            if content.turn_complete:
                                remainder = transcript.finish()
                                if remainder:
                                    pending_text += remainder
                                    spoken_text += remainder
                                if spoken_text:
                                    await asyncio.to_thread(emit, run_id, 'speech', {'text': spoken_text, 'audio_url': None})
                                if use_eleven:
                                    if pending_text:
                                        await playback.queue.put(pending_text)
                                pending_text = ''
                                spoken_text = ''
                                transcript = SpokenTranscript()
                        if response.tool_call:
                            await respond_to_tool_calls(ctx, session, response.tool_call.function_calls)
            await session.send_client_content(turns=types.Content(role='user', parts=[types.Part(text='The owner is on the line. Greet them briefly.')]), turn_complete=True)
            tasks = [asyncio.create_task(receive_caller()), asyncio.create_task(receive_gemini()), asyncio.create_task(playback.worker())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception('Voice session failed')
        if run_id:
            await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': 'context', 'status': 'failed', 'data': {'error': 'Voice session disconnected'}})
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if client:
            await client.aio.aclose()
        if run_id:
            await asyncio.to_thread(finish, run_id, 'closed')
