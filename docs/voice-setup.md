# Voice: browser call now, phone call when a number is wired

Span's voice has two entry points that share the same planner, tools and approvals.

## 1. Browser call (works today, no keys beyond Gemini)

- Home → **Call Span in the browser** (or the Ask page with `?voice=browser&call=1`), then
  **Call Span** in the dock. Span greets you aloud, listens, hands your words to the planner,
  speaks the answer and listens again until you press **Hang up**. **Mute** keeps Span silent (text only) while it keeps listening; it is remembered per browser until you press **Unmute**. A spoken "yes" or "not now"
  resolves the pending approval; anything else is a follow-up question in the same chat.
- The Home mic asks one question and opens the chat in call mode.
- Speech recognition is the browser's Web Speech API (Chrome, localhost or HTTPS).
- Span's voice is ElevenLabs when `ELEVEN_LABS_KEY` (or `ELEVENLABS_API_KEY`) is set, via
  `GET /voice/speech?text=…` (mp3). Without it the page falls back to the browser's own voice.
  `/health` → `voice.elevenlabs` tells you which one is active.
- It is a turn-based browser demo and the UI says so; it is not a telephone call.

## 2. Phone call (Twilio Media Streams → Gemini Live → ElevenLabs)

The bridge is implemented and tested without a carrier by `backend/scripts/call_smoke.py`
(it plays synthesized speech into `/voice/photon` exactly as Twilio would). To take real calls:

1. Set in `backend/.env` (never commit it):
   - `VOICE_STREAM_TOKEN` — any random secret, e.g. `openssl rand -hex 16`; it authenticates the
     media stream.
   - `TWILIO_AUTH_TOKEN` — from the Twilio console; it verifies the webhook signature.
   - `PUBLIC_BASE_URL` — the public **https** URL of this backend (for a laptop demo, an
     `ngrok http 8000` tunnel URL).
   - `VOICE_PHONE_NUMBER` — the number to show on Home, e.g. `+1 555 010 0000`.
   - Optional: `ELEVEN_LABS_KEY` for Span's voice (otherwise Gemini's own audio is used),
     `GEMINI_LIVE_MODEL` (default `gemini-3.8-live`).
2. Restart the backend. `/health` → `voice.phone` turns `true` and Home shows the number.
3. In Twilio, buy or pick a voice-capable number and set its **Voice → A call comes in** webhook
   to `POST https://<PUBLIC_BASE_URL>/voice/twiml`. Twilio then opens a Media Stream to
   `wss://<PUBLIC_BASE_URL>/voice/photon`.
4. Call the number. Span greets you, asks its one clarifying question when the books justify it,
   answers, and proposes one action; approvals still need your explicit yes.

Photon (the original telephony sponsor) publishes SIP rather than websocket media today, so the
Twilio route is the one that is wired. Nothing here buys or deploys anything by itself.

## Verify without a phone

```sh
cd backend
export VOICE_STREAM_TOKEN=$(openssl rand -hex 16)
.venv/bin/uvicorn owed.main:app --host 127.0.0.1 --port 8000 &
.venv/bin/python scripts/call_smoke.py      # six checks; report + assistant.wav in .local/call-smoke-<stamp>/
```
