#!/bin/sh
# Start the Photon Spectrum bridge with the credentials from backend/.env (SPECTRUM_PROJECT_ID, SPECTRUM_PROJECT_SECRET,
# PHOTON_WEBHOOK_TOKEN). Run from backend/:  scripts/spectrum_bridge.sh
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  while IFS= read -r line; do
    case "$line" in SPECTRUM_*=*|PHOTON_WEBHOOK_TOKEN=*|SPAN_INBOUND_URL=*|BRIDGE_PORT=*) export "$line" ;; esac
  done < .env
fi
: "${SPECTRUM_PROJECT_ID:?set SPECTRUM_PROJECT_ID in backend/.env (Photon dashboard → Settings → Credentials)}"
: "${SPECTRUM_PROJECT_SECRET:?set SPECTRUM_PROJECT_SECRET in backend/.env (same place, Reveal)}"
cd spectrum-bridge
[ -d node_modules ] || bun install
exec bun run bridge.ts
