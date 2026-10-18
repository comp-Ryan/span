"""GET /sponsors/checks: one live check per integration, so anyone can see what is wired, what is configured, and what answers right now.

Statuses: pass (answered), warn (reachable but degraded or partly configured), fail (configured but not answering),
off (not configured: the product runs its labeled fallback), info (build-time tool, nothing to call). Never echoes a secret."""
import asyncio
import time
from collections import Counter
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter

from owed.config import settings

router = APIRouter()
TIMEOUT = 8.0


def _db_scalar(sql, params=()):
    from owed.db import conn
    with conn() as c:
        row = c.execute(sql, params).fetchone()
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


async def check_gemini():
    if not settings.gemini_api_key:
        return 'off', 'GEMINI_API_KEY not set', False
    from google import genai
    from google.genai import errors, types
    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        await client.aio.models.generate_content(model=settings.gemini_model, contents='Reply with the single word ok.',
                                                 config=types.GenerateContentConfig(max_output_tokens=4))
        return 'pass', f'{settings.gemini_model} answered', True
    except errors.APIError as exc:
        if exc.code in (402, 429):
            return 'warn', f'{exc.code} from Gemini (credits or rate limit); the OpenRouter backup answers the planner instead', True
        return 'fail', f'{exc.code}: {str(exc)[:120]}', True


async def check_openrouter():
    if not settings.openrouter_api_key:
        return 'off', 'no OpenRouter key; Gemini only', False
    h = {'Authorization': 'Bearer ' + settings.openrouter_api_key}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get('https://openrouter.ai/api/v1/auth/key', headers=h)
        if r.status_code != 200:
            return 'fail', f'key check answered {r.status_code}', True
        cr = await c.get('https://openrouter.ai/api/v1/credits', headers=h)  # the account balance; the key's limit is only a cap
    chain = [m.strip() for m in settings.openrouter_model.split(',') if m.strip()]
    free = [m for m in chain if m.endswith(':free')]
    balance = None
    if cr.status_code == 200:
        d = cr.json().get('data') or {}
        try:
            balance = float(d.get('total_credits') or 0) - float(d.get('total_usage') or 0)
        except (TypeError, ValueError):
            balance = None
    if balance is not None and balance <= 0.01:
        if not free:
            return 'fail', 'key ok, but the account has no credit and no free model is in the chain', True
        return 'warn', f'key ok, account has no credit, so the free model answers ({free[0]})', True
    left = f'${balance:.2f} credit' if balance is not None else 'balance unknown'
    return 'pass', f'key ok, {left}; chain {chain[0]} → {chain[-1]}', True


async def check_elevenlabs():
    if not settings.elevenlabs_api_key:
        return 'off', 'no key; the browser falls back to its own speech synthesis', False
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:  # voices_read is the one permission every ElevenLabs key has
        r = await c.get('https://api.elevenlabs.io/v1/voices', headers={'xi-api-key': settings.elevenlabs_api_key})
    if r.status_code != 200:
        return 'fail', f'voices check answered {r.status_code}', True
    voices = r.json().get('voices') or []
    mine = next((v.get('name') for v in voices if v.get('voice_id') == settings.elevenlabs_voice_id), None)
    return ('pass' if mine else 'warn'), (f"key ok, {len(voices)} voices; Span speaks as {mine}" if mine else f'key ok, {len(voices)} voices, but ELEVENLABS_VOICE_ID is not among them'), True


async def check_tigerdata():
    version = await asyncio.to_thread(_db_scalar, "select extversion from pg_extension where extname='timescaledb'")
    tables = await asyncio.to_thread(_db_scalar, 'select count(*) from timescaledb_information.hypertables')
    rows = await asyncio.to_thread(_db_scalar, 'select count(*) from cash_projection')
    return 'pass', f'TimescaleDB {version}, {tables} hypertables, {rows:,} forecast rows in cash_projection', True


async def check_intuit():
    companies = await asyncio.to_thread(_db_scalar, 'select count(*) from companies')
    customers = await asyncio.to_thread(_db_scalar, 'select count(*) from customers')
    invoices = await asyncio.to_thread(_db_scalar, 'select count(*) from invoice_facts')
    return 'pass', f'{companies} companies, {customers:,} customers, {invoices:,} invoices loaded; dataset rows never modified', True


async def check_model():
    from owed.api import metrics
    m = metrics()['payment_model']
    return 'pass', f"days-late model: held-out MAE {m.get('mae_days')} days; write-off AUC {m.get('auc_write_off')} (5-fold)", True


async def check_uagents():
    base = settings.customer_agent_endpoint.rsplit('/', 1)[0]
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            await c.get(base + '/')
        reachable = True
    except httpx.HTTPError:
        reachable = False
    agentverse = bool(settings.agentverse_api_key and settings.agent_public_endpoint)
    if not reachable:
        return 'fail', f'customer-agent bureau not answering at {base} (start it with the backend); negotiation would wait', True
    return ('pass' if agentverse else 'warn'), f'bureau answering at {base}; ' + ('registered on Agentverse' if agentverse else 'Agentverse registration off (no AGENTVERSE_API_KEY), so not on ASI:One yet'), True


async def check_photon():
    if settings.spectrum_bridge_url:
        try:
            async with httpx.AsyncClient(timeout=4) as c:
                r = await c.get(settings.spectrum_bridge_url.rstrip('/') + '/health')
            if r.status_code == 200:
                return 'pass', f"Spectrum bridge up ({r.json().get('platform', 'imessage')}); reminders go to {"the owner's phone" if settings.photon_demo_recipient else 'no recipient set!'}", True
            return 'fail', f'bridge answered {r.status_code}', True
        except httpx.HTTPError:
            return 'fail', 'SPECTRUM_BRIDGE_URL set but the bridge is not running (backend/scripts/spectrum_bridge.sh)', True
    if settings.photon_api_key and settings.photon_project_id:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f'https://api.photon.codes/v1/projects/{settings.photon_project_id}/users?pageSize=1',
                            headers={'Authorization': 'Bearer ' + settings.photon_api_key})
        if r.status_code == 200:
            return ('pass' if settings.photon_sms_sender_id else 'warn'), 'v2 project reachable' + ('' if settings.photon_sms_sender_id else '; PHOTON_SMS_SENDER_ID missing, reminders stay simulated'), True
        hint = ' (project id is not a v2 pho_prj_ id)' if not settings.photon_project_id.startswith('pho_prj_') else ''
        return 'fail', f'v2 API answered {r.status_code}{hint}; reminders stay simulated', True
    return 'off', 'no Photon keys: reminders and replies are simulated and labeled', False


async def check_visa():
    from owed.payments import visa
    if visa.configured():
        return 'pass', 'sandbox credentials present; card payments post to the Visa sandbox', True
    return 'off', 'no sandbox credentials: the simulated card rail is used and labeled on the pay page', False


async def check_solana():
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(settings.solana_rpc_url, json={'jsonrpc': '2.0', 'id': 1, 'method': 'getVersion'})
        version = (r.json().get('result') or {}).get('solana-core', '?')
    except (httpx.HTTPError, ValueError):
        return 'fail', f'devnet RPC {settings.solana_rpc_url} not answering', bool(settings.solana_recipient)
    if settings.solana_recipient.strip():
        return 'pass', f'devnet RPC ok (solana-core {version}); USDC devnet rail active', True
    return 'warn', f'devnet RPC ok (solana-core {version}) but SOLANA_RECIPIENT not set, so the Solana rail is hidden', False


async def check_sentry():
    if not settings.sentry_dsn:
        return 'off', 'no DSN: SDK wired (Gemini integration), traces stay local', False
    import sentry_sdk
    return ('pass' if sentry_sdk.is_initialized() else 'fail'), 'SDK initialized, traces and logs upload' if sentry_sdk.is_initialized() else 'DSN set but SDK not initialized', True


async def check_phone():
    ready = bool(settings.gemini_api_key and settings.twilio_auth_token and settings.voice_stream_token)
    if ready:
        return 'pass', f"phone line {settings.voice_phone_number or 'configured'}: Twilio media stream → Gemini Live → ElevenLabs", True
    return 'off', 'browser call only (Web Speech + ElevenLabs); the phone bridge needs Twilio + Gemini credits', False


async def check_browser_use():
    from owed.portal import configured
    return ('pass', 'customer portal automation configured', True) if configured() else ('off', 'portal automation not configured', False)


async def check_hosting():
    local = any(h in settings.public_base_url for h in ('localhost', '127.0.0.1'))
    return ('off' if local else 'pass'), ('running locally; Vultr is the deployment target' if local else f'public base {settings.public_base_url}'), not local


async def check_build_tools():
    return 'info', 'design in Paper (QuickBooks-style canvas); Devin wrote data chunks; no runtime call', True


# Only what the running product actually calls. (Visa sandbox, Solana, Sentry, the phone line, Browser Use and Vultr are
# wired in code but unconfigured, so the product never calls them; they are not listed.)
CHECKS = [
    ('Gemini', 'Google: planner + Live voice', check_gemini),
    ('OpenRouter backup', 'planner failover, free models last', check_openrouter),
    ('ElevenLabs', 'voice of Span', check_elevenlabs),
    ('Tiger Data', 'TimescaleDB forecast history', check_tigerdata),
    ('Intuit dataset', 'books, customers, invoices', check_intuit),
    ('Model Learning', 'days-late scoring model', check_model),
    ('Fetch.ai uAgents', 'customer agents and negotiation', check_uagents),
    ('Photon', 'reminders as real iMessages', check_photon),
]


async def run_check(name, track, fn):
    started = time.monotonic()
    try:
        status, detail, configured = await asyncio.wait_for(fn(), TIMEOUT)
    except asyncio.TimeoutError:
        status, detail, configured = 'fail', f'no answer in {TIMEOUT:.0f}s', True
    except Exception as exc:  # a broken integration must never break the page
        status, detail, configured = 'fail', f'{type(exc).__name__}: {str(exc)[:140]}', True
    return {'name': name, 'track': track, 'status': status, 'detail': detail, 'configured': configured,
            'ms': int((time.monotonic() - started) * 1000)}


@router.get('/sponsors/checks')
async def sponsor_checks():
    rows = await asyncio.gather(*(run_check(*c) for c in CHECKS))
    return {'generated_at': datetime.now(UTC).isoformat(), 'checks': rows, 'summary': dict(Counter(r['status'] for r in rows))}
