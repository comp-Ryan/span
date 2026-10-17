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
from owed.events import emit
from owed.planner import TOOLS, ToolContext, system_prompt
from owed.runs import create, finish
from owed.runs.payroll import target_for

router = APIRouter()
log = logging.getLogger(__name__)


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
        run_id = await asyncio.to_thread(create, company, 'Live phone call', 'call', 'free_question')
        await asyncio.to_thread(emit, run_id, 'node.create', {'node_id': 'context', 'type': 'context',
            'title': 'Live phone call', 'status': 'running', 'parent': None})
        ctx = ToolContext(run_id, company, target_for('Friday'))
        playback = Playback(ws, meta['streamSid'])
        client = genai.Client(api_key=settings.gemini_api_key)
        use_eleven = bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)
        config = {'response_modalities': ['AUDIO'], 'input_audio_transcription': {},
                  'output_audio_transcription': {}, 'tools': [{'function_declarations': TOOLS}],
                  'system_instruction': system_prompt(company, ctx.target) + '\nKeep spoken turns brief. Begin by asking how you can help.'}
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
                pending_text, audio_state = '', None
                while True:
                    async for response in session.receive():
                        content = response.server_content
                        if content:
                            if content.interrupted:
                                pending_text = ''
                                await playback.interrupt()
                            if content.input_transcription and content.input_transcription.text:
                                await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': 'context',
                                    'data': {'caller_text': content.input_transcription.text}})
                            if content.output_transcription and content.output_transcription.text:
                                text = content.output_transcription.text
                                await asyncio.to_thread(emit, run_id, 'speech', {'text': text, 'audio_url': None})
                                pending_text += text
                                if use_eleven and (pending_text.rstrip().endswith(('.', '?', '!')) or len(pending_text) > 180):
                                    await playback.queue.put(pending_text)
                                    pending_text = ''
                            if not use_eleven and content.model_turn:
                                for part in content.model_turn.parts or []:
                                    if part.inline_data:
                                        pcm, audio_state = audioop.ratecv(part.inline_data.data, 2, 1, 24000, 8000, audio_state)
                                        await playback.media(audioop.lin2ulaw(pcm, 2))
                            if content.turn_complete and pending_text:
                                if use_eleven:
                                    await playback.queue.put(pending_text)
                                pending_text = ''
                        if response.tool_call:
                            for call in response.tool_call.function_calls:
                                result = await ctx.execute(call.name, call.args or {})
                                await session.send_tool_response(function_responses=[types.FunctionResponse(id=call.id, name=call.name, response=result)])
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
