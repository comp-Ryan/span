/**
 * Demo recorder: drives the running frontend (npm run dev) through the demo flow and writes
 * a 1440x900 screen recording, six 2x stills, and a 1500x900 Devpost thumbnail to demo-out/.
 *
 *   BASE_URL=http://127.0.0.1:5173 npm run record
 *
 * Deterministic: the frontend replays public/fixture.json; no backend needed.
 */
import { chromium, type Browser, type Page } from 'playwright'
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const BASE_URL = (process.env.BASE_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'demo-out')
const W = 1440, H = 900
const SEL = {
  title: 'h1.q', node: '.thread .node', gauge: '.verdict', call: '.callwrap', chart: '.chart',
  levers: '.levers', yes: '.lever button:has-text("Yes, text them")',
  action: '.action', reply: '.action:has-text("replied")', negotiation: '.action:has-text("Negotiating")',
  payment: '.action.paid:has-text("paid")',
  chip: '.sugg button:has-text("What if Evergreen")', followup: '.thread .branch',
  approve: '.thread button:has-text("Approve both")',
}
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const log = (s: string) => console.log(`[record] ${s}`)
/** Scroll so `sel` sits just under the sticky topbar (scrollIntoView would hide it behind the bar). */
const scrollTo = (page: Page, sel: string, offset = 88) => page.evaluate(([s, o]) => {
  const el = document.querySelector(s as string); if (!el) return
  window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - (o as number), behavior: 'smooth' })
}, [sel, offset])
const wait = (page: Page, sel: string, timeout = 120_000) => page.locator(sel).first().waitFor({ state: 'visible', timeout })

async function open(page: Page, speed = 1) {
  await page.goto(`${BASE_URL}/?speed=${speed}`, { waitUntil: 'domcontentloaded' })
  await wait(page, SEL.title)
}

/** The scripted path with natural pauses. Calls `at(step)` at each milestone so a pass can shoot stills. */
async function walk(page: Page, at: (step: string) => Promise<void> = async () => {}) {
  await wait(page, SEL.node); await at('question')
  await wait(page, SEL.gauge); await sleep(1500); await at('verdict')

  await page.hover(SEL.call); await sleep(3000)
  await page.mouse.move(W / 2, H - 40); await sleep(400)

  await wait(page, SEL.levers); await wait(page, SEL.yes); await sleep(800); await at('levers')
  await page.click(SEL.yes)
  await page.locator(SEL.action).nth(2).waitFor({ state: 'visible', timeout: 120_000 })
  await wait(page, SEL.reply); await wait(page, SEL.negotiation); await wait(page, SEL.payment)
  await sleep(600); await at('actions')

  await page.locator(SEL.chart).first().scrollIntoViewIfNeeded(); await sleep(2000)

  await page.locator(SEL.chip).first().scrollIntoViewIfNeeded()
  await page.click(SEL.chip)
  await wait(page, SEL.followup); await wait(page, SEL.approve)
  await scrollTo(page, SEL.followup); await sleep(2000); await at('followup')
  await page.click(SEL.approve); await sleep(1200)

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(1200)
}

async function stills(browser: Browser) {
  log('pass 1/2: stills (2x) + thumbnail')
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()
  const shot = (name: string) => page.screenshot({ path: join(OUT, name) })

  // 02-scoring: dots mid-tick. Scoring runs ~0.6 s to ~6.8 s into the replay at speed 1.
  await open(page, 1)
  const t0 = Date.now()
  await wait(page, SEL.node)
  await page.locator('.dots i').nth(8).waitFor({ timeout: 30_000 })
  await sleep(Math.max(0, 5000 - (Date.now() - t0)))
  await shot('02-scoring.png')

  // Reload for a clean take of the rest of the flow.
  await open(page, 1)
  await walk(page, async step => {
    if (step === 'question') await shot('01-question.png')
    if (step === 'verdict') {
      await shot('03-verdict.png')
      await thumbnail(page)
    }
    if (step === 'levers') await shot('04-levers.png')
    if (step === 'actions') {
      await page.locator(SEL.payment).first().scrollIntoViewIfNeeded(); await sleep(400)
      await shot('05-actions.png')
    }
    if (step === 'followup') await shot('06-followup.png')
  })
  await ctx.close()
}

/** 1500x900 (5:3): brand mark + question on the left, the verdict gauge card on the right. */
async function thumbnail(page: Page) {
  const question = (await page.locator(SEL.title).first().textContent())?.trim() || ''
  const verdict = page.locator(SEL.gauge).first()
  const word = (await verdict.locator('.big').textContent())?.trim() || ''
  const sub = (await verdict.locator('.sub').textContent())?.trim() || ''
  const card = (await verdict.screenshot({ type: 'png' })).toString('base64')
  const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'styles.css'), 'utf8')
  const rootVars = css.match(/:root\{[^}]*\}/)?.[0] || ''
  const thumb = await page.context().newPage()
  await thumb.setViewportSize({ width: 750, height: 450 })
  await thumb.setContent(`<!doctype html><html><head><style>
    ${rootVars}
    *{box-sizing:border-box}body{margin:0;width:750px;height:450px;overflow:hidden;background:var(--bg);color:var(--text);
      font:14px/1.4 var(--font);-webkit-font-smoothing:antialiased;
      background-image:radial-gradient(#CFD3D9 1px,transparent 1px);background-size:22px 22px}
    .wrap{display:flex;align-items:center;height:100%;padding:0 48px;gap:36px}
    .left{flex:1;display:flex;flex-direction:column;gap:22px;min-width:0}
    .brand{display:flex;align-items:center;gap:12px}
    .mark{width:44px;height:44px;border-radius:22px;background:var(--green);color:#fff;font-weight:700;font-size:22px;display:flex;align-items:center;justify-content:center}
    .name{font-size:26px;font-weight:600;letter-spacing:-.01em}
    .eyebrow{font-size:14px;color:var(--muted);display:flex;align-items:center;gap:8px}
    .dot{width:8px;height:8px;border-radius:4px;background:var(--green);display:inline-block}
    h1{margin:0;font-size:38px;line-height:44px;font-weight:700;letter-spacing:-.015em}
    .ans{font-size:20px;color:var(--muted);line-height:28px}.ans b{color:var(--text)}
    .card{flex-shrink:0;width:280px;display:flex;align-items:center;justify-content:center}
    .card img{width:280px;display:block;border-radius:12px;box-shadow:0 18px 44px rgba(57,58,61,.18)}
  </style></head><body><div class="wrap">
    <div class="left">
      <div class="brand"><div class="mark">O</div><div class="name">owed</div></div>
      <div class="eyebrow"><i class="dot"></i>Palletbay Storage &amp; Warehousing · by phone</div>
      <h1>${esc(question)}</h1>
      <div class="ans"><b>${esc(word)}</b> ${esc(sub)} — reasoned live from the books.</div>
    </div>
    <div class="card"><img src="data:image/png;base64,${card}" alt=""></div>
  </div></body></html>`)
  await thumb.screenshot({ path: join(OUT, 'thumbnail-1500x900.png'), clip: { x: 0, y: 0, width: 750, height: 450 } })
  await thumb.close()
}
const esc = (s: string) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]!)

async function video(browser: Browser) {
  log('pass 2/2: video (1x)')
  const vdir = join(OUT, '.video')
  rmSync(vdir, { recursive: true, force: true })
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, recordVideo: { dir: vdir, size: { width: W, height: H } } })
  const page = await ctx.newPage()
  await open(page, 1)
  await walk(page)
  await sleep(1500)
  const v = page.video()
  await ctx.close()
  const path = await v?.path()
  if (!path) throw new Error('no video recorded')
  renameSync(path, join(OUT, 'demo.webm'))
  rmSync(vdir, { recursive: true, force: true })
  const probe = spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' })
  if (probe.status === 0) {
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', join(OUT, 'demo.webm'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart', join(OUT, 'demo.mp4')])
    log('demo.mp4 written (ffmpeg)')
  } else log('ffmpeg not found: leaving demo.webm only')
}

async function main() {
  const started = Date.now()
  const ok = await fetch(BASE_URL).then(r => r.ok).catch(() => false)
  if (!ok) { console.error(`[record] nothing answering at ${BASE_URL}. Start it with: cd frontend && npm run dev`); process.exit(1) }
  mkdirSync(OUT, { recursive: true })
  for (const f of readdirSync(OUT)) if (/\.(png|webm|mp4)$/.test(f)) rmSync(join(OUT, f))
  const browser = await chromium.launch()
  try { await stills(browser); await video(browser) } finally { await browser.close() }
  const files = readdirSync(OUT).filter(f => !f.startsWith('.')).sort()
  for (const f of files) log(`${f.padEnd(24)} ${(statSync(join(OUT, f)).size / 1024).toFixed(0).padStart(6)} KB`)
  const missing = ['01-question.png', '02-scoring.png', '03-verdict.png', '04-levers.png', '05-actions.png', '06-followup.png', 'thumbnail-1500x900.png', 'demo.webm'].filter(f => !existsSync(join(OUT, f)))
  if (missing.length) throw new Error(`missing outputs: ${missing.join(', ')}`)
  log(`done in ${((Date.now() - started) / 1000).toFixed(0)} s -> ${OUT}`)
}

main().catch(e => { console.error(e); process.exit(1) })
