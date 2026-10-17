# Owed frontend

Vite + React. Replays `public/fixture.json` (the Palletbay payroll run) as a growing reasoning canvas by default; `?live` subscribes to the backend over SSE (proxied from `/api` to `127.0.0.1:8000`); `?speed=N` speeds the replay.

```bash
npm install
npm run dev        # http://127.0.0.1:5173
npm run build
npm run lint
```

## Demo recorder (`npm run record`)

Produces the raw Devpost assets from the running frontend, with no clicking: a screen recording of the full demo flow, six stills, and a 5:3 thumbnail. Driven by Playwright (`scripts/record_demo.ts`), deterministic against the fixture replay, ~90 s end to end.

```bash
npm run dev                      # in one terminal (or anywhere; see BASE_URL)
npx playwright install chromium  # once
npm run record                   # BASE_URL=http://127.0.0.1:5174 npm run record if 5173 is taken
```

Outputs in `demo-out/` (gitignored):

| file | what |
|---|---|
| `demo.webm` | 1440×900 recording: question → scoring → verdict → transcript hover → "Yes, text them" → reminders, reply, negotiation, payment → cash chart → follow-up "What if Evergreen doesn’t pay?" → "Approve both" |
| `demo.mp4` | same, H.264, only if `ffmpeg` is on `PATH` (otherwise the script says so and leaves the webm) |
| `01-question.png` … `06-followup.png` | 2× stills (2880×1800): question + first node, scoring dots mid-tick, verdict gauge, levers, actions (negotiation + payment), follow-up thread |
| `thumbnail-1500x900.png` | exactly 1500×900: brand mark, the question, and the verdict gauge card |

The scripted path waits on the UI's own selectors (`h1.q`, `.verdict`, `.callwrap`, `.levers`, `.action.paid`, `.sugg button`, `.thread .branch`), so timing changes in the fixture don't break it; a selector change in `src/App.tsx` would.
