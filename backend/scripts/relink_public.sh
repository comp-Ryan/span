#!/bin/sh
# Re-open the public link to the local Span backend and point youare.cooking at it.
# Run from the repo root when the site's "Try Span live" stops working:  sh backend/scripts/relink_public.sh
set -e
LOG=/tmp/span-cloudflared.log
pkill -f "cloudflared tunnel" 2>/dev/null || true
nohup cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 > "$LOG" 2>&1 &
URL=""
for i in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "cloudflared gave no URL; see $LOG"; exit 1; }
printf '{"api": "%s"}\n' "$URL" > site/config.json
git add site/config.json
git commit -q -m "Project site: relink the live app ($URL)" || true
git push -q origin HEAD
git branch -D gh-pages -q 2>/dev/null || true
git subtree split --prefix site -b gh-pages -q
git push -q -f origin gh-pages
echo "Live app: $URL/home  (youare.cooking picks it up within about a minute)"
