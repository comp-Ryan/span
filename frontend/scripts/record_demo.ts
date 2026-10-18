/**
 * Demo recorder (task 5). One command produces the Devpost assets from the
 * running frontend: demo.webm screen recording, six PNG stills at 2x, and a
 * 1500x900 thumbnail. Run `npm run dev` first, or set BASE_URL; if the URL is
 * unreachable the dev server is started for you.
 *
 *   npm run record            -> frontend/demo-out/*
 *   BASE_URL=http://127.0.0.1:5188 npm run record
 *   SPEED=3 npm run record    -> faster fixture replay
 *   PLAYWRIGHT_BROWSERS_PATH / `npx playwright install chromium` for the
 *   bundled browser; falls back to the installed Chrome channel automatically.
 */
import { chromium, type Browser, type Page } from 'playwright'
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { mkdirSync, readdirSync, renameSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const BASE = (process.env.BASE_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const SPEED = process.env.SPEED || '1'
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'demo-out')
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

const URL_ = `${BASE}/?speed=${SPEED}`

async function ensureServer(): Promise<ChildProcess | undefined> {
  try {
    const r = await fetch(BASE, { signal: AbortSignal.timeout(2000) })
    if (r.ok) return undefined
  } catch { /* start one */ }
  console.log(`[record] ${BASE} not reachable, starting vite…`)
  const child = spawn('npx', ['vite', '--port', new URL(BASE).port || '5173', '--strictPort'], { cwd: dirname(OUT), stdio: 'pipe' })
  for (let i = 0; i < 60; i++) {
    await sleep(1000)
    try { if ((await fetch(BASE)).ok) return child } catch { /* not up yet */ }
  }
  throw new Error(`dev server did not come up at ${BASE}`)
}

async function launch(): Promise<Browser> {
  try { return await chromium.launch() }
  catch { return await chromium.launch({ channel: 'chrome' }) }
}

/* ---------- the scripted path, shared by the video and stills passes ---------- */
async function clickYes(page: Page) {
  await page.getByRole('button', { name: 'Yes, text them' }).click()
}
async function clickAccept(page: Page) {
  const b = page.getByRole('button', { name: 'Accept' }).first()
  await b.waitFor({ timeout: 10_000 }).catch(() => {})
  await b.click().catch(() => {})
}
async function openDock(page: Page) {
  const b = page.locator('.dock .bubble')
  if (await b.count()) await b.click()
}
async function closeDock(page: Page) {
  const h = page.locator('.dock .dhead')
  if (await h.count()) await h.click()
}
async function followUp(page: Page) {
  await openDock(page)
  await page.locator('.dock .sugg button', { hasText: 'Evergreen' }).first().click()
  await page.locator('.thread').nth(1).waitFor()
  const approve = page.getByRole('button', { name: 'Approve both' })
  await approve.waitFor()
  await sleep(2000)
  await approve.click()
}

/* ---------- pass 1: screen recording ---------- */
async function recordVideo(browser: Browser) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
  })
  const page = await ctx.newPage()
  await page.goto(URL_, { waitUntil: 'domcontentloaded' })
  await page.locator('h1.q').waitFor()
  await page.locator('.verdict').waitFor()
  await sleep(1500)

  // call transcript (the dock is a click-to-open bubble now, not a hover pill)
  await openDock(page)
  await sleep(3000)
  await closeDock(page)

  await page.locator('.levers').waitFor()
  await clickYes(page)
  await page.locator('.conv').nth(2).waitFor()          // three reminders
  await page.locator('.bub.in').first().waitFor()       // customer reply
  await page.locator('.neg').first().waitFor()          // negotiation
  await clickAccept(page)
  await page.locator('.receipt', { hasText: 'received' }).waitFor() // payment

  const chart = page.locator('.chart.card').first()
  await chart.scrollIntoViewIfNeeded()
  await sleep(2000)

  await followUp(page)
  await page.locator('.main').evaluate(el => el.scrollTo(0, 0)).catch(() => {})
  await page.evaluate(() => window.scrollTo(0, 0))
  await sleep(1200)

  await ctx.close() // finalizes the .webm
  const webm = readdirSync(OUT).filter(f => f.endsWith('.webm')).sort().pop()
  if (webm && webm !== 'demo.webm') renameSync(join(OUT, webm), join(OUT, 'demo.webm'))
  console.log('[record] demo.webm written')
}

/* ---------- pass 2: stills at 2x ---------- */
async function stills(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()
  const shot = (n: string) => page.screenshot({ path: join(OUT, n) })
  await page.goto(URL_, { waitUntil: 'domcontentloaded' })

  await page.locator('h1.q').waitFor()
  await page.locator('.vstep .node').first().waitFor()
  await sleep(400)
  await shot('01-question.png')

  await page.waitForFunction(() => document.querySelectorAll('.dots i').length >= 36, null, { timeout: 60_000 })
  await shot('02-scoring.png')

  await page.locator('.verdict').waitFor()
  await page.waitForFunction(() => document.querySelector('.card.status .big')?.textContent?.trim().length)
  await sleep(300)
  await shot('03-verdict.png')

  await page.locator('.levers').waitFor()
  await page.waitForTimeout(500)
  await shot('04-levers.png')

  // thumbnail region: brand + question + verdict gauge + chart, exactly 5:3
  const dock = await page.locator('.dock').elementHandle()
  await dock?.evaluate((el: HTMLElement) => { el.style.display = 'none' })
  const raw = await page.screenshot({ clip: { x: 0, y: 0, width: 1440, height: 864 } })
  await sharp(raw).resize(1500, 900).png().toFile(join(OUT, 'thumbnail-1500x900.png'))
  await dock?.evaluate((el: HTMLElement) => { el.style.display = '' })

  await clickYes(page)
  await page.locator('.neg').first().waitFor()
  await clickAccept(page)
  await page.locator('.receipt', { hasText: 'received' }).waitFor()
  await page.locator('.convs').scrollIntoViewIfNeeded()
  await sleep(400)
  await shot('05-actions.png')

  await followUp(page)
  await page.locator('.thread').nth(1).scrollIntoViewIfNeeded()
  await sleep(400)
  await shot('06-followup.png')
  await ctx.close()
  console.log('[record] stills + thumbnail written')
}

/* ---------- mp4 when ffmpeg exists ---------- */
function convert() {
  const has = spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0
  if (!has) { console.log('[record] ffmpeg not found — leaving demo.webm (no mp4)'); return }
  const r = spawnSync('ffmpeg', ['-y', '-i', join(OUT, 'demo.webm'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', join(OUT, 'demo.mp4')], { stdio: 'inherit' })
  if (r.status === 0) console.log('[record] demo.mp4 written')
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const server = await ensureServer()
  try {
    const browser = await launch()
    try {
      await stills(browser)          // shorter flow first so timings are exercised once
      await recordVideo(browser)
    } finally { await browser.close() }
    convert()
    console.log(`[record] done -> ${OUT}`)
  } finally { server?.kill() }
}
main().catch(e => { console.error(e); process.exit(1) })
