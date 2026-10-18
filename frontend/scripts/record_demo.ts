/** Live demo: isolated fresh DB → Gemini clarification → real approval → local agents → simulated card.
 * No fixture/event injection and no real customer messages or charges. `npm run record:fixture` is offline only.
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
const STAMP = new Date().toISOString().replace(/[^0-9]/g, '')
const OUT = join(ROOT, 'frontend/demo-out', `live-${STAMP}`)
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const children: ChildProcess[] = []
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.once(signal, () => { for (const child of children) child.kill('SIGTERM'); process.exit(130) })
let rootRun: string | undefined
let manifest: { database: string; env_file: string }

function command(exe: string, args: string[], cwd = ROOT) {
  const p = spawnSync(exe, args, { cwd, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 })
  if (p.status !== 0) throw new Error(`${exe} failed: ${p.stderr || p.stdout}`)
  return p.stdout.trim()
}
async function available(port: number) {
  await new Promise<void>((ok, fail) => {
    const server = createServer(); server.once('error', () => fail(new Error(`Port ${port} is in use; choose RECORD_PORT / RECORD_AGENT_PORT. No existing process was killed.`)))
    server.listen(port, '127.0.0.1', () => server.close(() => ok()))
  })
}
async function json(path: string) {
  const r = await fetch(BASE + path, { signal: AbortSignal.timeout(5000) })
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}
async function until<T>(read: () => Promise<T>, done: (value: T) => boolean, label: string, timeout = 120000): Promise<T> {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await read()
    if (done(value)) return value
    await sleep(500)
  }
  throw new Error(`Timed out: ${label}. Inspect failure.png and backend.log; no result was fabricated.`)
}
const replay = (id: string) => json(`/api/runs/${id}?company=${COMPANY}`)
async function waitAnswer(id: string) {
  const r = await until(() => replay(id), r => r.events.some((e: any) => e.event === 'run.end'), 'planner answer', 180000)
  const failed = r.events.find((e: any) => e.event === 'node.create' && e.data.status === 'failed')
  if (failed) throw new Error(`Live planner failed: ${failed.data.data?.error || failed.data.title}. Check Gemini key/model/credits; stopping.`)
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
  await sleep(800)
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true })
  console.log(`[record] ${name}`)
}
async function liveFlow(page: Page) {
  await page.goto(`${BASE}/home?company=${COMPANY}`)
  await page.getByTestId('ask-card').waitFor()
  await shot(page, '01-home')
  // Browser voice uses the actual planner but the recording contains typed input, not a claimed phone call.
  await page.goto(`${BASE}/?live&new=1&voice=browser&company=${COMPANY}`)
  rootRun = await ask(page, 'Am I going to make payroll these next two weeks? Evergreen may be late.')
  const initial = await waitAnswer(rootRun)
  if (!initial.events.some((e: any) => e.data.data?.awaiting_input)) throw new Error('Expected a one-question clarification; the model did not ask one. Stopping instead of staging it.')
  await page.getByText('Span needs one answer', { exact: true }).waitFor()
  await shot(page, '02-clarification')
  await page.locator('.dock .dhead').click()
  const branch = await ask(page, 'Treat Evergreen Juniper Flats Removals as not paying by payday. Forecast the same two weeks and show me who to chase.')
  await waitAnswer(branch)
  await page.getByRole('button', { name: 'Yes, text them', exact: true }).waitFor({ timeout: 120000 })
  await page.locator('.levers').last().scrollIntoViewIfNeeded()
  await shot(page, '03-forecast-approval')
  const before = await replay(branch)
  if (before.events.some((e: any) => e.data.data?.kind === 'reminder')) throw new Error('Approval guard failed: reminder before Yes')
  const approvalResponse = page.waitForResponse(r => r.url().includes('/api/decisions/') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Yes, text them', exact: true }).click()
  if (!(await approvalResponse).ok()) throw new Error('The real decision endpoint rejected Yes')
  const settled = await until(() => replay(branch), r => r.events.some((e: any) => e.data.data?.agreement?.installments?.length), 'local uAgent agreement', 180000)
  const reminders = settled.events.filter((e: any) => e.event === 'node.create' && e.data.data?.kind === 'reminder')
  if (reminders.length !== 3 || reminders.some((e: any) => e.data.data.channel !== 'simulated')) throw new Error('Expected exactly three disclosed simulated reminders')
  await page.locator('.agree').last().waitFor({ timeout: 30000 })
  await page.locator('.msgs').last().scrollIntoViewIfNeeded()
  await shot(page, '04-messages-negotiation')
  const installment = settled.events.find((e: any) => e.data.data?.agreement?.installments?.length).data.data.agreement.installments[0]
  // Use the actual pay link listed by Get paid; no API payment shortcuts.
  await page.goto(`${BASE}/get-paid?company=${COMPANY}`)
  const pay = page.locator(`a[href="/api/pay/${installment.pay_token}/page"]`).first()
  await pay.waitFor(); await page.goto(BASE + await pay.getAttribute('href'))
  await page.locator('#cc-number').fill('4111111111111111')
  await page.locator('#cc-exp').fill('12/28'); await page.locator('#cc-cvv').fill('123')
  await page.locator('#cc-name').fill('Demo customer')
  await page.locator('#visa-btn').click()
  await page.locator('#receipt:not(.hidden)').waitFor()
  await shot(page, '05-payment-receipt')
  await until(() => replay(branch), r => r.events.some((e: any) => e.data.data?.kind === 'payment'), 'payment event')
  await page.goto(`${BASE}/?live&run=${rootRun}&company=${COMPANY}`)
  await page.locator('.receipt').last().waitFor({ timeout: 30000 })
  await page.getByTestId('forecast-history').last().scrollIntoViewIfNeeded()
  await shot(page, '06-reforecast-history')
  await sharp(await page.screenshot()).resize(1500, 900, { fit: 'cover' }).png().toFile(join(OUT, 'thumbnail-1500x900.png'))
  // Verify sidebar rename stays per root and reload restores this branch.
  await page.locator('h1.q').dblclick()
  await page.getByRole('textbox', { name: 'Rename chat', exact: true }).fill('Payroll planning')
  await page.getByRole('textbox', { name: 'Rename chat', exact: true }).press('Enter')
  await page.reload(); await page.getByRole('heading', { name: 'Payroll planning', exact: true }).waitFor()
  await page.locator(`[data-run-id="${branch}"]`).waitFor()
  const late = await ask(page, "Show me who's late")
  await until(() => replay(late), r => r.events.some((e: any) => e.event === 'run.end'), 'late branch')
  await page.locator('.latelist').waitFor(); await page.locator('.latelist').scrollIntoViewIfNeeded()
  await shot(page, '07-follow-up')
  const whatIf = await ask(page, "What if Evergreen doesn't pay?")
  await until(() => replay(whatIf), r => r.events.some((e: any) => e.event === 'run.end'), 'Evergreen what-if branch')
  await page.locator(`[data-run-id="${whatIf}"] .verdict`).waitFor()
  await page.goto(`${BASE}/reports?company=${COMPANY}`)
  await shot(page, '08-reports')
  const reportLink = page.locator('a[href^="/report/"]').first()
  await reportLink.waitFor()
  await page.goto(BASE + await reportLink.getAttribute('href'))
  await page.locator('a[href$=".pdf"], a[href*=".pdf?"]').first().waitFor()
  await shot(page, '09-report')
  const pdfPath = await page.locator('a[href*=".pdf"]').first().getAttribute('href')
  const pdf = await fetch(BASE + pdfPath)
  const pdfBytes = Buffer.from(await pdf.arrayBuffer())
  if (!pdf.ok || pdfBytes.subarray(0, 5).toString() !== '%PDF-') throw new Error('Report PDF did not render')
  writeFileSync(join(OUT, 'report.pdf'), pdfBytes)
  const saved = await json(`/api/runs?company=${COMPANY}`)
  const evidence = { mode: 'live', company: COMPANY, rootRun, branch, late, whatIf, database: manifest.database,
    disclosure: 'Real Gemini and local uAgents. Simulated messages/customer reply/card payment. No live phone-call or Tiger Cloud claim.',
    runs: await Promise.all(saved.runs.map((r: any) => replay(r.run_id))),
    forecasts: await json(`/api/forecasts?company=${COMPANY}`), paymentAmount: installment.amount }
  writeFileSync(join(OUT, 'evidence.json'), JSON.stringify(evidence, null, 2))
  await page.goto(`${BASE}/?live&new=1&company=${COMPANY}`)
  if (await page.locator('[data-run-id]').count()) throw new Error('New chat did not clear the canvas')
  console.log(`[record] live end-to-end passed; paid ${installment.amount}; outcome reflects actual remaining gap`)
}
async function main() {
  mkdirSync(OUT, { recursive: true })
  await available(PORT); await available(AGENT_PORT)
  const missing = JSON.parse(command(PYTHON, ['-c', 'import json; from owed.config import settings; print(json.dumps([k.upper() for k in ("gemini_api_key", "agent_seed") if not getattr(settings, k)]))'], BACKEND)) as string[]
  if (missing.length) throw new Error(`Missing ${missing.join(', ')} in backend/.env. Stopping.`)
  command('npm', ['run', 'build'], join(ROOT, 'frontend'))
  manifest = JSON.parse(command(PYTHON, ['backend/scripts/demo_db.py', 'create', '--name', `span_demo_record_${STAMP}`]))
  const database = readFileSync(manifest.env_file, 'utf8').split('\n').find(s => s.startsWith('DATABASE_URL='))!.slice(13)
  const env = { ...process.env, DATABASE_URL: database, DEMO_COMPANY: COMPANY, PUBLIC_BASE_URL: BASE,
    INTERNAL_API_URL: BASE, AGENT_PORT: String(AGENT_PORT), CUSTOMER_AGENT_ENDPOINT: `${BASE.replace(String(PORT), String(AGENT_PORT))}/submit`,
    PHOTON_API_KEY: '', PHOTON_PROJECT_ID: '', VISA_USER_ID: '', VISA_PASSWORD: '', AGENTVERSE_API_KEY: '', SENTRY_DSN: '', SCORING_INTERVAL_MS: '0' }
  const start = (args: string[], log: string) => {
    const fd = openSync(join(OUT, log), 'w', 0o600)
    const child = spawn(PYTHON, args, { cwd: BACKEND, env, stdio: ['ignore', fd, fd] }); children.push(child); return child
  }
  start(['-m', 'uvicorn', 'owed.main:app', '--host', '127.0.0.1', '--port', String(PORT)], 'backend.log')
  start(['-m', 'owed.agents.runtime'], 'agents.log')
  await until(async () => { try { return await json('/api/health') } catch { return null } }, h => !!h?.gemini, 'isolated API startup', 30000)
  await sleep(3000)
  writeFileSync(join(ROOT, '.local/latest-recording.json'), JSON.stringify({ ...manifest, base: BASE, output: OUT }, null, 2))
  let browser
  try { browser = await chromium.launch() } catch { browser = await chromium.launch({ channel: 'chrome' }) }
  const context = await browser.newContext({ viewport: { width: 1500, height: 900 }, recordVideo: { dir: OUT, size: { width: 1500, height: 900 } } })
  const page = await context.newPage(); page.setDefaultTimeout(30000)
  try { await liveFlow(page) }
  catch (e) {
    await page.screenshot({ path: join(OUT, 'failure.png'), fullPage: true }).catch(() => {})
    if (rootRun) writeFileSync(join(OUT, 'failed-run.json'), JSON.stringify(await replay(rootRun), null, 2))
    throw e
  } finally {
    const video = page.video(); await context.close(); if (video) await video.saveAs(join(OUT, 'demo.webm')); await browser.close()
  }
  if (spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0) command('ffmpeg', ['-y', '-i', join(OUT, 'demo.webm'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', join(OUT, 'demo.mp4')])
  console.log(`[record] outputs: ${OUT}`)
}
main().catch(e => { console.error(String(e)); process.exitCode = 1 }).finally(async () => {
  for (const child of children) child.kill('SIGTERM')
  await Promise.all(children.map(child => child.exitCode !== null ? Promise.resolve() : new Promise(resolve => child.once('exit', resolve))))
})
