/**
 * Live demo recorder. Drives the real product end to end (no fixture, no injected events) and writes
 * demo.webm, numbered stills and the 1500x900 thumbnail to frontend/demo-out/live-<stamp>/.
 *
 * Each take: a fresh isolated clone of the local Timescale database (backend/scripts/demo_db.py),
 * its own API + local customer-agent bureau on spare ports, the built frontend, then:
 *   Home → ask "Am I going to make payroll these next two weeks?" (browser-voice planner path, typed)
 *   → Span asks its one clarifying question → owner answers → verdict + "Yes, text them"
 *   → real approval → three simulated reminders → simulated customer replies + local uAgent negotiation
 *   → pay the first installment of each agreement on the real pay page (Visa sandbox / simulated card)
 *   → outcome card (green only if the collected cash really covers the gap)
 *   → follow-up "What if Evergreen doesn't pay?" → Get paid → Reports → the report + PDF.
 * Gemini latency is real; nothing is staged. If a step never happens the take fails with failure.png.
 *
 *   npm run record                      (RECORD_PORT / RECORD_AGENT_PORT to pick other ports)
 *   npm run record:fixture              offline fixture replay, kept separately
 */
import { chromium, type Page } from 'playwright'
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync, openSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import sharp from 'sharp'

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const BACKEND = join(ROOT, 'backend'), PYTHON = join(BACKEND, '.venv/bin/python')
const PORT = Number(process.env.RECORD_PORT || 8028), AGENT_PORT = Number(process.env.RECORD_AGENT_PORT || 8029)
const BASE = `http://127.0.0.1:${PORT}`, COMPANY = 'company-020'
const QUESTION = 'Am I going to make payroll these next two weeks?'
const CLARIFY_ANSWER = process.env.RECORD_CLARIFY || "I'm not sure, go with your estimate."
const WHAT_IF = "What if Evergreen doesn't pay?"
const STAMP = new Date().toISOString().replace(/[^0-9]/g, '')
const OUT = join(ROOT, 'frontend/demo-out', `live-${STAMP}`)
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const children: ChildProcess[] = []
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => { for (const child of children) child.kill('SIGTERM'); process.exit(130) })
let rootRun: string | undefined
let manifest: { database: string; env_file: string }
const log = (line: string) => console.log(`[record ${new Date().toISOString().slice(11, 19)}] ${line}`)

function command(exe: string, args: string[], cwd = ROOT) {
  const p = spawnSync(exe, args, { cwd, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 })
  if (p.status !== 0) throw new Error(`${exe} ${args.join(' ')} failed: ${p.stderr || p.stdout}`)
  return p.stdout.trim()
}
async function available(port: number) {
  await new Promise<void>((ok, fail) => {
    const server = createServer(); server.once('error', () => fail(new Error(`Port ${port} is in use; set RECORD_PORT / RECORD_AGENT_PORT. No existing process was killed.`)))
    server.listen(port, '127.0.0.1', () => server.close(() => ok()))
  })
}
async function json(path: string) {
  const r = await fetch(BASE + path, { signal: AbortSignal.timeout(8000) })
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}
async function until<T>(read: () => Promise<T>, done: (value: T) => boolean, label: string, timeout = 120000): Promise<T> {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await read()
    if (done(value)) return value
    await sleep(600)
  }
  throw new Error(`Timed out: ${label}. See failure.png and backend.log; nothing was fabricated.`)
}
const replay = (id: string) => json(`/api/runs/${id}?company=${COMPANY}`)
const ended = (r: any) => r.events.some((e: any) => e.event === 'run.end')
async function waitAnswer(id: string, label: string) {
  const r = await until(() => replay(id), ended, label, 240000)
  const failed = r.events.find((e: any) => e.event === 'node.create' && e.data.status === 'failed')
  if (failed) throw new Error(`Live planner failed (${label}): ${failed.data.data?.error || failed.data.title}. Check Gemini key/model/credits.`)
  return r
}
async function ask(page: Page, question: string) {
  const response = page.waitForResponse(r => r.url().includes('/api/ask?') && r.request().method() === 'POST')
  const input = page.getByRole('textbox', { name: 'Ask Span', exact: true })
  await input.fill(question); await input.press('Enter')
  const r = await response
  if (!r.ok()) throw new Error(`Ask failed: ${await r.text()}`)
  return (await r.json()).run_id as string
}
async function shot(page: Page, name: string) {
  await sleep(900)
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true })
  log(name)
}
async function payFirstInstallment(page: Page, token: string, amount: number, first: boolean) {
  // The real pay link listed on Get paid; the card is the Visa sandbox / simulated rail, never a live charge.
  await page.goto(`${BASE}/get-paid?company=${COMPANY}`)
  const link = page.locator(`a[href="/api/pay/${token}/page"]`).first()
  await link.waitFor()
  if (first) await shot(page, '05-get-paid-links')
  await page.goto(BASE + await link.getAttribute('href'))
  await page.locator('#cc-number').fill('4111111111111111')
  await page.locator('#cc-exp').fill('12/28'); await page.locator('#cc-cvv').fill('123')
  await page.locator('#cc-name').fill('Demo customer')
  await page.locator('#visa-btn').click()
  await page.locator('#receipt:not(.hidden)').waitFor()
  if (first) await shot(page, '06-payment-receipt')
  log(`paid installment ${amount} on ${token}`)
}

async function liveFlow(page: Page) {
  await page.goto(`${BASE}/home?company=${COMPANY}`)
  await page.getByTestId('ask-card').waitFor()
  await page.getByTestId('forecast-trend').waitFor()
  await shot(page, '01-home')

  // The browser-voice route sends the question to the Gemini planner; the recording types it (no live call is claimed).
  await page.goto(`${BASE}/?live&new=1&voice=browser&company=${COMPANY}`)
  rootRun = await ask(page, QUESTION)
  const initial = await waitAnswer(rootRun, 'first answer')
  const answer = initial.events.find((e: any) => e.event === 'node.create' && e.data.node_id === 'answer')?.data?.data
  if (!answer?.awaiting_input) throw new Error(`Expected one clarifying question, got: ${answer?.spoken}. Stopping instead of staging it.`)
  await page.getByText('Span needs one answer', { exact: true }).waitFor()
  await page.locator('.dock .dhead').click()
  await shot(page, '02-clarifying-question')

  const branch = await ask(page, CLARIFY_ANSWER)
  const forecasted = await waitAnswer(branch, 'forecast after the owner answered')
  const approvalButton = page.getByRole('button', { name: 'Yes, text them', exact: true })
  await approvalButton.waitFor({ timeout: 60000 })
  await page.locator('.levers').last().scrollIntoViewIfNeeded()
  const verdict = forecasted.events.find((e: any) => e.event === 'node.create' && e.data.node_id === 'answer')?.data?.data
  log(`verdict: ${verdict?.spoken}`)
  await shot(page, '03-verdict-approval')
  if ((await replay(branch)).events.some((e: any) => e.data.data?.kind === 'reminder')) throw new Error('Approval guard failed: a reminder exists before Yes')

  const approval = page.waitForResponse(r => r.url().includes('/api/decisions/') && r.request().method() === 'POST')
  await approvalButton.click()
  if (!(await approval).ok()) throw new Error('The real decision endpoint rejected Yes')
  const settled = await until(() => replay(branch), r => r.events.filter((e: any) => e.data.data?.agreement?.installments?.length).length >= 1, 'first local uAgent agreement', 240000)
  const reminders = settled.events.filter((e: any) => e.event === 'node.create' && e.data.data?.kind === 'reminder')
  if (!reminders.length || reminders.some((e: any) => e.data.data.channel !== 'simulated')) throw new Error('Expected disclosed simulated reminders after Yes')
  // Let the other negotiations finish (they run in parallel); stop waiting when no new agreement arrives for a while.
  let agreements = settled.events.filter((e: any) => e.data.data?.agreement?.installments?.length)
  for (let quiet = 0; quiet < 25 && agreements.length < reminders.length; quiet++) {
    await sleep(2000)
    const now = (await replay(branch)).events.filter((e: any) => e.data.data?.agreement?.installments?.length)
    if (now.length > agreements.length) { agreements = now; quiet = 0 }
  }
  await page.locator('.agree').first().waitFor({ timeout: 30000 })
  await page.locator('.msgs').last().scrollIntoViewIfNeeded()
  await shot(page, '04-messages-negotiation')
  log(`${reminders.length} simulated reminders, ${agreements.length} agreements`)

  const installments = agreements.map((e: any) => e.data.data.agreement.installments[0])
  for (const [i, inst] of installments.entries()) await payFirstInstallment(page, inst.pay_token, inst.amount, i === 0)
  await until(() => replay(branch), r => r.events.filter((e: any) => e.data.data?.kind === 'payment').length >= installments.length, 'payment events', 90000)

  await page.goto(`${BASE}/?live&run=${rootRun}&company=${COMPANY}`)
  await page.locator('.receipt').last().waitFor({ timeout: 30000 })
  const outcome = page.locator('.card.outcome').last()
  await outcome.waitFor({ timeout: 30000 })
  // Green only when the refreshed forecast really covers payroll; otherwise record what it shows.
  const covered = await (async () => {
    try {
      await page.waitForFunction(() => {
        const cols = document.querySelectorAll('.card.outcome .d-col b'); const now = cols[cols.length - 1] as HTMLElement | undefined
        return !!now && now.style.color.includes('green')
      }, null, { timeout: 60000 })
      return true
    } catch { return false }
  })()
  await outcome.scrollIntoViewIfNeeded()
  log(covered ? 'outcome card is green: payroll covered after the payments' : 'outcome card still shows a shortfall (not forced green)')
  await shot(page, '07-outcome')
  await page.getByTestId('forecast-history').last().scrollIntoViewIfNeeded().catch(() => {})
  await sharp(await page.screenshot()).resize(1500, 900, { fit: 'cover', position: 'top' }).png().toFile(join(OUT, 'thumbnail-1500x900.png'))

  const whatIf = await ask(page, WHAT_IF)
  await waitAnswer(whatIf, 'Evergreen what-if')
  await page.locator(`[data-run-id="${whatIf}"]`).waitFor()
  await page.locator(`[data-run-id="${whatIf}"]`).scrollIntoViewIfNeeded()
  await shot(page, '08-what-if-evergreen')

  await page.goto(`${BASE}/get-paid?company=${COMPANY}`)
  await page.getByText('Payments received', { exact: false }).first().waitFor().catch(() => {})
  await shot(page, '09-get-paid')
  await page.goto(`${BASE}/reports?company=${COMPANY}`)
  const reportLink = page.locator('a[href^="/report/"]').first()
  await reportLink.waitFor({ timeout: 120000 })
  await shot(page, '10-reports')
  await page.goto(BASE + await reportLink.getAttribute('href'))
  await page.locator('a[href*=".pdf"]').first().waitFor()
  await shot(page, '11-report')
  const pdf = await fetch(BASE + await page.locator('a[href*=".pdf"]').first().getAttribute('href'))
  const pdfBytes = Buffer.from(await pdf.arrayBuffer())
  if (!pdf.ok || pdfBytes.subarray(0, 5).toString() !== '%PDF-') throw new Error('Report PDF did not render')
  writeFileSync(join(OUT, 'report.pdf'), pdfBytes)

  const saved = await json(`/api/runs?company=${COMPANY}`)
  const evidence = {
    mode: 'live', company: COMPANY, database: manifest.database, question: QUESTION, clarifying_answer: CLARIFY_ANSWER,
    rootRun, branch, whatIf, verdict: verdict?.spoken, reminders: reminders.length, agreements: agreements.length,
    paid: installments.map((i: any) => ({ pay_token: i.pay_token, amount: i.amount })), payroll_covered_after_payments: covered,
    disclosure: 'Real Gemini planner and local uAgents on an isolated copy of the books. Simulated reminders, customer replies and card payments. Typed browser interaction, not a phone call. Local TimescaleDB, no Tiger Cloud claim.',
    runs: await Promise.all(saved.runs.map((r: any) => replay(r.run_id))),
    forecast_history: await json(`/api/cash/history?company=${COMPANY}`),
  }
  writeFileSync(join(OUT, 'evidence.json'), JSON.stringify(evidence, null, 2))
  log(`live end-to-end passed; paid ${installments.length} installment(s); covered=${covered}`)
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  await available(PORT); await available(AGENT_PORT)
  const missing = JSON.parse(command(PYTHON, ['-c', 'import json; from owed.config import settings; print(json.dumps([k.upper() for k in ("gemini_api_key", "agent_seed") if not getattr(settings, k)]))'], BACKEND)) as string[]
  if (missing.length) throw new Error(`Missing ${missing.join(', ')} in backend/.env. Stopping.`)
  command('npm', ['run', 'build'], join(ROOT, 'frontend'))
  manifest = JSON.parse(command(PYTHON, ['backend/scripts/demo_db.py', 'create', '--name', `span_demo_record_${STAMP}`]))
  log(`fresh isolated database ${manifest.database}`)
  const database = readFileSync(manifest.env_file, 'utf8').split('\n').find(s => s.startsWith('DATABASE_URL='))!.slice(13)
  const env = { ...process.env, DATABASE_URL: database, DEMO_COMPANY: COMPANY, PUBLIC_BASE_URL: BASE,
    INTERNAL_API_URL: BASE, AGENT_PORT: String(AGENT_PORT), CUSTOMER_AGENT_ENDPOINT: `http://127.0.0.1:${AGENT_PORT}/submit`,
    PHOTON_API_KEY: '', PHOTON_PROJECT_ID: '', VISA_USER_ID: '', VISA_PASSWORD: '', AGENTVERSE_API_KEY: '', SENTRY_DSN: '', SCORING_INTERVAL_MS: '0' }
  const start = (args: string[], logName: string) => {
    const fd = openSync(join(OUT, logName), 'w', 0o600)
    const child = spawn(PYTHON, args, { cwd: BACKEND, env, stdio: ['ignore', fd, fd] }); children.push(child); return child
  }
  start(['-m', 'uvicorn', 'owed.main:app', '--host', '127.0.0.1', '--port', String(PORT)], 'backend.log')
  start(['-m', 'owed.agents.runtime'], 'agents.log')
  await until(async () => { try { return await json('/api/health') } catch { return null } }, h => !!h?.gemini, 'isolated API startup', 60000)
  await sleep(4000)
  writeFileSync(join(ROOT, '.local/latest-recording.json'), JSON.stringify({ ...manifest, base: BASE, output: OUT }, null, 2))
  let browser
  try { browser = await chromium.launch() } catch { browser = await chromium.launch({ channel: 'chrome' }) }
  const context = await browser.newContext({ viewport: { width: 1500, height: 900 }, recordVideo: { dir: OUT, size: { width: 1500, height: 900 } } })
  const page = await context.newPage(); page.setDefaultTimeout(30000)
  try { await liveFlow(page) }
  catch (e) {
    await page.screenshot({ path: join(OUT, 'failure.png'), fullPage: true }).catch(() => {})
    if (rootRun) writeFileSync(join(OUT, 'failed-run.json'), JSON.stringify(await replay(rootRun).catch(() => null), null, 2))
    throw e
  } finally {
    const video = page.video(); await context.close(); if (video) await video.saveAs(join(OUT, 'demo.webm')); await browser.close()
  }
  if (spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0) command('ffmpeg', ['-y', '-i', join(OUT, 'demo.webm'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', join(OUT, 'demo.mp4')])
  log(`outputs: ${OUT}`)
}
main().catch(e => { console.error(String(e)); process.exitCode = 1 }).finally(async () => {
  for (const child of children) child.kill('SIGTERM')
  await Promise.all(children.map(child => child.exitCode !== null ? Promise.resolve() : new Promise(resolve => child.once('exit', resolve))))
})
