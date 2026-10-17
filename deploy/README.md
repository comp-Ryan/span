# Vultr deployment

The backend worktree lives inside the main project at `owed-backend/`, branch `astra/backend`.

Prerequisites: a Vultr Ubuntu host with Docker Compose, SSH access, and an API-domain A record pointing at its IP. Allow inbound 22, 80 and 443. PostgreSQL stays on the private Compose network. No deployment has occurred until the public health check succeeds.

1. Put service keys in `backend/.env`. Required for the full demo: Gemini, Photon Beta project + sender IDs + demo recipient + webhook token, ElevenLabs key + voice, Twilio auth + voice token (Photon offers SIP, so voice uses the authorized fallback), and Agentverse key + stable agent seed. Sentry DSN enables cloud monitoring.
2. Copy `deploy/.env.example` to `deploy/.env`; set `API_DOMAIN` and a URL-safe random `POSTGRES_PASSWORD`.
3. Run `backend/.venv/bin/python deploy/deploy.py --host root@HOST` from this worktree. It stages code, trained model and env files; exports the local database; restores only into an empty new deployment database; starts services and checks health. It never overwrites an already-loaded remote database.
4. Set Twilio inbound voice URL to `https://API_DOMAIN/voice/twiml`. Set Photon Beta callback URL to `https://API_DOMAIN/inbound/photon?token=WEBHOOK_TOKEN`; choose the message event and confirm its payload against the configured API version. The callback retrieves authoritative message data before classification. Caddy and uvicorn access logging are disabled so the callback token is not logged.
5. Verify `/companies`, `/model/metrics`, POST `/ask`, SSE `/events`, then a reminder → reply → negotiation → simulated payment → report. Visa is explicitly simulated without sandbox credentials; Agentverse discovery still needs a live ASI:One test.

Database bootstrap uses the existing Docker database on local port 5433. The trained pickle is copied as a deployment artifact, not committed to Git. Keep scikit-learn compatible with its training environment. Default Compose images should be pinned to the verified digests before the final production freeze.

API reference: https://www.vultr.com/api/ . If provisioning a host through the API, use the account's live `/v2/plans`, `/v2/regions`, `/v2/os`, and `/v2/ssh-keys` listings rather than guessing IDs. Creating an instance incurs account charges.

## Product frontend

`cd frontend && npm ci && npm run build` writes compiled assets into
`backend/owed/static/` (ignored by Git). Restart the API after the first build. FastAPI
serves the product at `/`, real mode at `/?live`, existing runs at `/?live&run=...`, and
the one-page report at `/report/:id`. API requests work under `/api/*`; all original
unprefixed endpoints are retained for callbacks/pay links. `/hub` still serves the
submission hub; `/hub/api/*` is unchanged. The Vite dev proxy remains available.

The production Dockerfile performs this build in a Node stage, then copies only the
compiled assets into the Python image. `deploy.py` transfers the frontend source and
lockfile (not node_modules or frontend environment secrets) so the remote build is
reproducible. Caddy forwards the product, `/api`, and `/hub` to FastAPI; no additional
Node server or nginx is required. Set `PUBLIC_BASE_URL=https://API_DOMAIN` for pay links.
