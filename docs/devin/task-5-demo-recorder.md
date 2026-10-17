# Devin task 5: demo recorder (video footage, screenshots, Devpost thumbnail)

**Goal.** One command that produces the raw assets for the Devpost submission from the running frontend: a screen recording of the full demo flow, six still screenshots, and a 5:3 thumbnail. Deterministic, repeatable, no humans clicking.

**Read first.** `docs/devin/README.md`; `frontend/` (Vite + React; `npm run dev` on :5173; demo replay is the default, `?live` uses the backend; `?speed=N` speeds the replay). The frontend replays `frontend/public/fixture.json` with original timing (~90 s).

**Build** in `frontend/scripts/record_demo.ts` using Playwright (`@playwright/test` or `playwright`, Chromium, add as devDependency):
1. Start from `http://127.0.0.1:5173/` (assume the dev server is running; also accept `BASE_URL`). Viewport 1440×900, deviceScaleFactor 2 for stills, 1 for video. Record video at 1440×900 to `frontend/demo-out/demo.webm`.
2. Scripted path with natural pauses:
   - wait for the question title; wait until the gauge card appears; pause 1.5 s
   - hover the call pill (`.callwrap`) for 3 s so the transcript panel shows; move away
   - wait for the levers; click "Yes, text them"; wait for 3 action cards, the reply card, the negotiation card, and the payment card (text "paid")
   - scroll the chart into view, pause 2 s
   - click the follow-up chip "What if Evergreen doesn’t pay?"; wait for the follow-up thread and its "Approve both" button; pause 2 s; click it
   - scroll back to top; end
3. Stills (PNG, 2×) into `frontend/demo-out/`: `01-question.png` (title + first node), `02-scoring.png` (dots mid-tick, use `?speed=1` and capture at ~5 s), `03-verdict.png` (gauge visible), `04-levers.png`, `05-actions.png` (negotiation + payment), `06-followup.png`.
4. Thumbnail: `frontend/demo-out/thumbnail-1500x900.png` at exactly 1500×900 (5:3): crop of the verdict gauge + question title region from a 2× screenshot, with the brand mark. Use sharp or Playwright's `clip`. Keep it simple and legible at small size.
5. Convert video to MP4 if ffmpeg is available (`demo.mp4`), otherwise leave webm and say so.
6. `npm run record` script in `frontend/package.json`. README section in `frontend/README.md` with the command and outputs.

**Acceptance.** `cd frontend && npm run record` produces demo.webm (and mp4 if ffmpeg), 6 PNGs, and the 1500×900 thumbnail, in under 3 minutes, with no manual steps. Attach the thumbnail and two stills to the PR.

**PR.** Branch `devin/demo-recorder`. Don't modify `frontend/src/` except to add stable `data-testid` attributes if a selector is unreliable; keep such edits minimal and list them in the PR.
