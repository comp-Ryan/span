#!/usr/bin/env python3
"""Phone-bot smoke test without Twilio.

Synthesizes caller speech with macOS `say`, converts it to 8 kHz mono mu-law with `afconvert`,
and streams it to ws://<backend>/voice/photon exactly as Twilio Media Streams would
(`connected`, `start`, 20 ms `media` frames, `stop`). While the call runs it polls the run the
bridge creates and checks: greeting, transcribed question, tool calls, spoken answer, one
clarifying question, and an answer to a follow-up. The assistant's audio is saved as a WAV.

The backend must have VOICE_STREAM_TOKEN in its environment (it is not in .env). Run from backend/:

  VOICE_STREAM_TOKEN=<same token> .venv/bin/python scripts/call_smoke.py [--base http://127.0.0.1:8000]
      [--company company-020] [--question ...] [--clarify-answer ...] [--followup ...] [--out DIR]

Exit code 0 only when every check passes; the JSON report always says what really happened.
"""
import argparse
import asyncio
import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

FRAME = 160  # 20 ms of 8 kHz mu-law
MULAW_SILENCE = b'\xff'
ROOT = Path(__file__).resolve().parents[2]


# ---------- audio helpers (pure; unit-tested) ----------

def wav_mulaw_payload(data: bytes) -> bytes:
    """Raw sample bytes from a RIFF WAVE file that must be 8 kHz mono mu-law (format tag 7)."""
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError('Not a RIFF/WAVE file')
    pos, fmt, payload = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack('<I', data[pos + 4:pos + 8])[0]
        chunk = data[pos + 8:pos + 8 + size]
        if cid == b'fmt ':
            fmt = struct.unpack('<HHI', chunk[:8])
        elif cid == b'data':
            payload = chunk
        pos += 8 + size + (size & 1)
    if fmt is None or payload is None:
        raise ValueError('WAVE file is missing fmt or data')
    tag, channels, rate = fmt
    if tag != 7 or channels != 1 or rate != 8000:
        raise ValueError(f'Expected 8 kHz mono mu-law, got tag={tag} channels={channels} rate={rate}')
    return payload


def frames(ulaw: bytes, size: int = FRAME) -> list:
    """Split into 20 ms frames; the last one is padded with mu-law silence."""
    out = [ulaw[i:i + size] for i in range(0, len(ulaw), size)]
    if out and len(out[-1]) < size:
        out[-1] = out[-1] + MULAW_SILENCE * (size - len(out[-1]))
    return out


def silence(seconds: float) -> bytes:
    return MULAW_SILENCE * int(8000 * seconds)


def mulaw_wav(ulaw: bytes) -> bytes:
    fmt = struct.pack('<HHIIHH', 7, 1, 8000, 8000, 1, 8)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(ulaw)) + ulaw
    return b'RIFF' + struct.pack('<I', len(body)) + body


def synthesize(text: str, workdir: Path, name: str) -> bytes:
    """macOS say -> afconvert -> 8 kHz mono mu-law bytes."""
    aiff, wav = workdir / f'{name}.aiff', workdir / f'{name}.ulaw.wav'
    subprocess.run(['say', '-o', str(aiff), text], check=True)
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'ulaw@8000', '-c', '1', str(aiff), str(wav)], check=True)
    return wav_mulaw_payload(wav.read_bytes())


# ---------- run assessment (pure; unit-tested) ----------

def assess(events: list) -> dict:
    """What the bridge's run shows: speech turns in order, tool calls, failure, and the six checks."""
    turns, tools, failed, ended = [], [], None, None
    for e in events:
        d = e.get('data') or {}
        if e.get('event') == 'speech':
            caller = d.get('kind') == 'caller' or d.get('speaker') == 'caller'
            text = (d.get('text') or '').strip()
            if text:
                turns.append(('caller' if caller else 'assistant', text, len(tools)))
        elif e.get('event') == 'node.create' and str(d.get('node_id', '')).startswith('tool-'):
            tools.append((d.get('data') or {}).get('tool') or d.get('title'))
        elif e.get('event') == 'node.update' and d.get('node_id') == 'context' and d.get('status') == 'failed':
            failed = (d.get('data') or {}).get('error', 'failed')
        elif e.get('event') == 'run.end':
            ended = d.get('status')
    caller_turns = [t for who, t, _ in turns if who == 'caller']
    first_caller = next((i for i, (who, _, _) in enumerate(turns) if who == 'caller'), None)
    greeting = next((t for who, t, _ in turns[:first_caller] if who == 'assistant'), None) if first_caller is not None else None
    clarifying = [t for i, (who, t, _) in enumerate(turns)
                  if who == 'assistant' and first_caller is not None and i > first_caller and t.rstrip().endswith('?')
                  and i + 1 < len(turns) and turns[i + 1][0] == 'caller']
    spoken_answer = next((t for who, t, n in turns if who == 'assistant' and n > 0), None)
    last_caller = max((i for i, (who, _, _) in enumerate(turns) if who == 'caller'), default=None)
    answer_at = next((i for i, (who, t, _) in enumerate(turns) if who == 'assistant' and t == spoken_answer), None)
    followup_answer = None
    if last_caller is not None and answer_at is not None and last_caller > answer_at:
        followup_answer = next((t for who, t, _ in turns[last_caller + 1:] if who == 'assistant'), None)
    checks = {'greeting': greeting is not None, 'transcribed_question': bool(caller_turns), 'tool_calls': bool(tools),
              'spoken_answer': spoken_answer is not None, 'one_clarifying_question': len(clarifying) == 1,
              'followup_answered': followup_answer is not None}
    return {'greeting': greeting, 'caller_turns': caller_turns, 'tool_calls': tools, 'clarifying_questions': clarifying,
            'spoken_answer': spoken_answer, 'followup_answer': followup_answer, 'failed': failed, 'ended': ended,
            'turns': [{'who': who, 'text': t} for who, t, _ in turns], 'checks': checks}


# ---------- the simulated Twilio call ----------

def http_json(url: str):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


class Call:
    def __init__(self, base: str, company: str, token: str, out: Path, log):
        self.base, self.company, self.token, self.out, self.log = base.rstrip('/'), company, token, out, log
        self.ws = None
        self.received = bytearray()
        self.clears = 0
        self.closed = None
        self.run_id = None
        self.stream = 'MZ' + os.urandom(8).hex()

    def runs(self):
        return {r['run_id']: r for r in http_json(f'{self.base}/api/runs?company={self.company}')['runs']}

    def events(self):
        return http_json(f'{self.base}/api/runs/{self.run_id}?company={self.company}')['events']

    async def receiver(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get('event') == 'media':
                    self.received += base64.b64decode(msg['media']['payload'])
                elif msg.get('event') == 'clear':
                    self.clears += 1
        except Exception as exc:  # closed by the bridge or the network
            self.closed = f'{type(exc).__name__}: {exc}'
        else:
            self.closed = 'closed'

    async def send_audio(self, ulaw: bytes):
        """Real-time pacing: one 20 ms frame every 20 ms, like a carrier."""
        start = time.monotonic()
        for i, frame in enumerate(frames(ulaw)):
            await self.ws.send(json.dumps({'event': 'media', 'streamSid': self.stream,
                                           'media': {'payload': base64.b64encode(frame).decode()}}))
            await asyncio.sleep(max(0.0, start + (i + 1) * 0.02 - time.monotonic()))

    async def wait_for(self, predicate, label: str, timeout: float):
        """Poll the run while streaming silence, so the bridge keeps hearing a live line."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.closed:
                raise RuntimeError(f'websocket ended while waiting for {label}: {self.closed}')
            events = self.events()
            if predicate(events):
                return events
            await self.send_audio(silence(0.5))
        raise TimeoutError(f'no {label} within {timeout:.0f}s')

    @staticmethod
    def assistant_turns(events):
        return [e for e in events if e['event'] == 'speech' and (e.get('data') or {}).get('kind') != 'caller'
                and (e.get('data') or {}).get('speaker') != 'caller']

    async def say(self, ulaw: bytes, label: str, timeout: float):
        before = len(self.assistant_turns(self.events()))
        self.log(f'caller: {label}')
        await self.send_audio(ulaw + silence(1.2))
        events = await self.wait_for(lambda ev: len(self.assistant_turns(ev)) > before, f'reply to {label}', timeout)
        text = (self.assistant_turns(events)[-1]['data'].get('text') or '').strip()
        self.log(f'assistant: {text}')
        return text

    async def run(self, utterances: dict, timeout: float):
        import websockets
        known = set(self.runs())
        ws_url = self.base.replace('https://', 'wss://').replace('http://', 'ws://') + '/voice/photon'
        async with websockets.connect(ws_url, max_size=None) as ws:
            self.ws = ws
            await ws.send(json.dumps({'event': 'connected', 'protocol': 'Call', 'version': '1.0.0'}))
            await ws.send(json.dumps({'event': 'start', 'sequenceNumber': '1', 'streamSid': self.stream, 'start': {
                'streamSid': self.stream, 'accountSid': 'ACsmoke', 'callSid': 'CAsmoke', 'tracks': ['inbound'],
                'customParameters': {'token': self.token, 'company': self.company},
                'mediaFormat': {'encoding': 'audio/x-mulaw', 'sampleRate': 8000, 'channels': 1}}}))
            receiver = asyncio.create_task(self.receiver())
            try:
                deadline = time.monotonic() + 15
                while self.run_id is None and time.monotonic() < deadline:
                    if self.closed:
                        raise RuntimeError(f'bridge closed the stream before creating a run: {self.closed}')
                    new = [r for rid, r in self.runs().items() if rid not in known and r.get('source') == 'call']
                    if new:
                        self.run_id = sorted(new, key=lambda r: r['started_at'])[-1]['run_id']
                    else:
                        await self.send_audio(silence(0.3))
                if self.run_id is None:
                    raise RuntimeError('the bridge never created a call run')
                self.log(f'run {self.run_id}')
                await self.wait_for(lambda ev: bool(self.assistant_turns(ev)), 'greeting', timeout)
                self.log(f"assistant: {self.assistant_turns(self.events())[-1]['data'].get('text', '').strip()}")
                reply = await self.say(utterances['question'], 'question', timeout)
                for _ in range(2):  # at most two clarifying questions before an answer
                    if not reply.rstrip().endswith('?'):
                        break
                    reply = await self.say(utterances['clarify'], 'clarifying answer', timeout)
                await self.say(utterances['followup'], 'follow-up', timeout)
                await ws.send(json.dumps({'event': 'stop', 'streamSid': self.stream}))
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not any(e['event'] == 'run.end' for e in self.events()):
            await asyncio.sleep(0.5)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--base', default='http://127.0.0.1:8000')
    p.add_argument('--company', default='company-020')
    p.add_argument('--token', default=os.environ.get('VOICE_STREAM_TOKEN', ''))
    p.add_argument('--question', default='Am I going to make payroll these next two weeks?')
    p.add_argument('--clarify-answer', default='No. Treat Evergreen as not paying.')
    p.add_argument('--followup', default='And what if Evergreen does pay by payday?')
    p.add_argument('--timeout', type=float, default=90, help='seconds to wait for each spoken reply')
    p.add_argument('--out', help='report directory (default .local/call-smoke-<stamp>)')
    a = p.parse_args()
    if not a.token:
        sys.exit('VOICE_STREAM_TOKEN is not set. Start the backend with it, e.g.\n'
                 '  VOICE_STREAM_TOKEN=$(openssl rand -hex 16) .venv/bin/uvicorn owed.main:app --port 8000\n'
                 'and pass the same value here with --token or the environment.')
    out = Path(a.out) if a.out else ROOT / '.local' / f'call-smoke-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    out.mkdir(parents=True, exist_ok=True)
    log_lines = []

    def log(line):
        log_lines.append(f'{time.strftime("%H:%M:%S")} {line}')
        print(log_lines[-1], flush=True)

    sys.path.insert(0, str(ROOT / 'backend'))
    from owed.config import settings
    report = {'base': a.base, 'company': a.company, 'live_model': settings.gemini_live_model,
              'elevenlabs': bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id), 'started': time.ctime()}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        utterances = {'question': synthesize(a.question, work, 'question'),
                      'clarify': synthesize(a.clarify_answer, work, 'clarify'),
                      'followup': synthesize(a.followup, work, 'followup')}
        for name, ulaw in utterances.items():
            (out / f'caller-{name}.wav').write_bytes(mulaw_wav(ulaw))
    call = Call(a.base, a.company, a.token, out, log)
    error = None
    try:
        asyncio.run(call.run(utterances, a.timeout))
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        log(f'ERROR {error}')
    events = call.events() if call.run_id else []
    result = assess(events)
    if call.received:
        (out / 'assistant.wav').write_bytes(mulaw_wav(bytes(call.received)))
    report.update(result, run_id=call.run_id, error=error, websocket=call.closed,
                  audio_seconds_received=round(len(call.received) / 8000, 2), barge_in_clears=call.clears,
                  log=log_lines)
    if result['failed'] or (error and not result['checks']['greeting']):
        report['live_model_accepted'] = False
    elif result['checks']['greeting']:
        report['live_model_accepted'] = True
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print('=' * 80)
    for check, ok in result['checks'].items():
        print(f"{'PASS' if ok else 'FAIL'} {check}")
    print(f"live model {settings.gemini_live_model}: {'accepted' if report.get('live_model_accepted') else 'NOT accepted or unknown'}"
          f" · audio received {report['audio_seconds_received']}s · report {out / 'report.json'}")
    sys.exit(0 if all(result['checks'].values()) and not error else 1)


if __name__ == '__main__':
    main()
