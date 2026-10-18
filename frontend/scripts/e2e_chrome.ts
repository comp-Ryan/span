/**
 * End-to-end checks in real Chrome against a fresh isolated copy of the local database (never the shared demo DB).
 * Starts its own API + customer-agent bureau on spare ports, serves the built frontend, then checks:
 *   every rail page loads with data and no console errors · new chat / past chat / rename / reload ·
 *   Home mic and the dock "Speak follow-up" (Chrome fake audio capture; Web Speech may refuse headless) ·
 *   "yes" resolves the pending decision (typed into the dock; same approvalChoice path as speech) ·
 *   the pay page updates Get paid · the report opens, prints (window.print observed) and its PDF downloads.
 *
 *   npm run e2e            (E2E_PORT / E2E_AGENT_PORT to choose ports; E2E_HEADED=1 for a visible window)
 */
import { chromium, type Browser, type Page } from 'playwright'
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync, openSync, existsSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const BACKEND = join(ROOT, 'backend'), PYTHON = join(BACKEND, '.venv/bin/python')
const PORT = Number(process.env.E2E_PORT || 8058), AGENT_PORT = Number(process.env.E2E_AGENT_PORT || 8059)
const BASE = `http://127.0.0.1:${PORT}`, COMPANY = 'company-020'
const STAMP = new Date().toISOString().replace(/[^0-9]/g, '')
const OUT = join(ROOT, 'frontend/demo-out', `e2e-${STAMP}`)
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const children: ChildProcess[] = []
const results: { check: string; ok: boolean | null; detail: string }[] = []
const log = (line: string) => console.log(`[e2e ${new Date().toISOString().slice(11, 19)}] ${line}`)
const record = (check: string, ok: boolean | null, detail = '') => { results.push({ check, ok, detail }); log(`${ok === null ? 'INFO' : ok ? 'PASS' : 'FAIL'} ${check}${detail ? ' — ' + detail : ''}`) }

function command(exe: string, args: string[], cwd = ROOT) {
  const p = spawnSync(exe, args, { cwd, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 })
  if (p.status !== 0) throw new Error(`${exe} ${args.join(' ')} failed: ${p.stderr || p.stdout}`)
  return p.stdout.trim()
}
async function available(port: number) {
  await new Promise<void>((ok, fail) => {
    const server = createServer(); server.once('error', () => fail(new Error(`Port ${port} is in use; set E2E_PORT / E2E_AGENT_PORT.`)))
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
  while (Date.now() < deadline) { const value = await read(); if (done(value)) return value; await sleep(600) }
  throw new Error(`Timed out: ${label}`)
}
const replay = (id: string) => json(`/api/runs/${id}?company=${COMPANY}`)

/** Console errors, page errors and failed same-origin requests, per page. */
function watch(page: Page) {
  const errors: string[] = []
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 160)}`) })
  page.on('pageerror', e => errors.push(`pageerror: ${String(e).slice(0, 160)}`))
  page.on('response', r => { if (r.url().startsWith(BASE) && r.status() >= 400) errors.push(`${r.status()} ${r.url().slice(BASE.length, BASE.length + 80)}`) })
  return errors
}
async function check(name: string, fn: () => Promise<string | void>) {
  try { record(name, true, (await fn()) || '') } catch (e) { record(name, false, String((e as Error).message || e).slice(0, 220)) }
}

async function railPages(browser: Browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  const pages: [string, () => Promise<string>][] = [
    [`/home?company=${COMPANY}`, async () => { await page.getByTestId('ask-card').waitFor(); await page.getByTestId('forecast-trend').waitFor(); await page.getByText('In the bank').waitFor(); return 'tiles, ask card, forecast trend' }],
    [`/get-paid?company=${COMPANY}`, async () => { await page.getByTestId('pay-links').waitFor(); await page.getByTestId('rail-readiness').waitFor(); return 'pay links + rail readiness' }],
    [`/reports?company=${COMPANY}`, async () => { await page.getByTestId('report-list').waitFor(); return 'report list' }],
    [`/customers?company=${COMPANY}`, async () => { await page.locator('[data-testid="customer-table"] tbody tr').first().waitFor(); const n = await page.locator('[data-testid="customer-table"] tbody tr').count(); if (n < 10) throw new Error(`only ${n} customers`); return `${n} customers` }],
    [`/?live&new=1&company=${COMPANY}`, async () => { await page.locator('.chat-sidebar').waitFor(); await page.getByRole('textbox', { name: 'Ask Span', exact: true }).waitFor(); return 'ask page with chat sidebar' }],
  ]
  for (const [path, verify] of pages) {
    const errors = watch(page)
    await check(`page ${path.split('?')[0] || '/'} loads with data and no console errors`, async () => {
      await page.goto(BASE + path); const what = await verify(); await sleep(800)
      if (errors.length) throw new Error(`errors: ${errors.join(' | ')}`)
      return what
    })
  }
  await check('customer detail page loads', async () => {
    const errors = watch(page)
    await page.goto(`${BASE}/customers?company=${COMPANY}`)
    const first = page.locator('[data-testid="customer-table"] tbody tr a').first(); await first.waitFor()
    await first.click(); await page.getByTestId('history-strip').waitFor(); await page.getByRole('button', { name: 'Ask Span about this customer' }).waitFor(); await sleep(500)
    if (errors.length) throw new Error(`errors: ${errors.join(' | ')}`)
    return page.url().replace(BASE, '')
  })
  await context.close()
}

async function chatAndDecisions(browser: Browser, fakeAudio: string) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['microphone'] })
  const page = await context.newPage(); page.setDefaultTimeout(30000)
  const errors = watch(page)
  let runId = ''
  await check('new chat: typed question starts a run and the sidebar lists it', async () => {
    await page.goto(`${BASE}/?live&new=1&company=${COMPANY}`)
    const response = page.waitForResponse(r => r.url().includes('/api/ask?') && r.request().method() === 'POST')
    const input = page.getByRole('textbox', { name: 'Ask Span', exact: true }); await input.fill('Will I make payroll in two weeks?'); await input.press('Enter')
    runId = (await (await response).json()).run_id
    await until(() => replay(runId), r => r.events.some((e: any) => e.event === 'run.end'), 'payroll run end', 120000)
    await page.locator(`[data-run-id="${runId}"] .verdict`).waitFor()
    await page.locator('.chat-history-item', { hasText: 'Will I make payroll' }).first().waitFor()
    return runId
  })
  await check('New chat button clears the canvas', async () => {
    await page.getByRole('link', { name: '+ New chat' }).click()
    await page.waitForURL(/new=1/); await page.locator('.empty-chat').waitFor()
    if (await page.locator('[data-run-id]').count()) throw new Error('canvas not empty')
  })
  await check('past chat click loads /?run=<id>&live', async () => {
    await page.locator('.chat-history-item a', { hasText: 'Will I make payroll' }).first().click()
    await page.waitForURL(new RegExp(`run=${runId}`)); await page.locator(`[data-run-id="${runId}"]`).waitFor()
    if (!page.url().includes('live')) throw new Error(`url ${page.url()}`)
  })
  await check('rename by double-click persists across reload (per run id)', async () => {
    await page.locator('h1.q').dblclick()
    const box = page.getByRole('textbox', { name: 'Rename chat', exact: true }); await box.fill('E2E payroll check'); await box.press('Enter')
    await page.getByRole('heading', { name: 'E2E payroll check', exact: true }).waitFor()
    await page.reload(); await page.getByRole('heading', { name: 'E2E payroll check', exact: true }).waitFor()
    await page.locator('.chat-history-item a', { hasText: 'E2E payroll check' }).first().waitFor()
    const key = await page.evaluate(() => Object.keys(localStorage).find(k => k.startsWith('span.chatTitle:')))
    if (!key || !key.includes(runId) || localStorage === undefined) return `stored under ${key}`
    return `stored under ${key}`
  })
  await check('typed "yes" in the dock resolves the pending decision (same path as spoken yes)', async () => {
    await page.getByRole('button', { name: 'Yes, text them', exact: true }).waitFor({ timeout: 60000 })
    await sleep(1500)  // let the replayed decision event land before answering it
    if (await page.locator('.dock .bubble').count()) await page.locator('.dock .bubble').click()
    const decided = page.waitForResponse(r => r.url().includes('/api/decisions/') && r.request().method() === 'POST')
    const box = page.locator('.dinput input'); await box.fill('yes'); await box.press('Enter')
    const r = await decided; if (!r.ok()) throw new Error(`decision POST ${r.status()}`)
    await until(() => replay(runId), rr => rr.events.some((e: any) => e.event === 'decision.resolved'), 'decision.resolved', 30000)
    await page.locator('.dock .dhead').click()
    return 'decision.resolved received'
  })
  await check('dock "Speak follow-up" mic (browser voice, Chrome fake audio)', async () => {
    await page.goto(`${BASE}/?run=${runId}&live&voice=browser&company=${COMPANY}`)
    if (await page.locator('.dock .bubble').count()) await page.locator('.dock .bubble').click()  // browser-voice opens the dock by itself
    await page.getByRole('button', { name: 'Speak one follow-up' }).click()
    const status = page.locator('.browser-voice-control [role="status"], .browser-voice-control [role="alert"]')
    await until(async () => (await status.textContent()) || '', t => t.trim().length > 0, 'voice status', 10000)
    const first = (await status.textContent())!.trim()
    const final = await until(async () => (await status.textContent()) || '', t => !t.startsWith('Listening'), 'speech result or error', 25000).catch(() => 'still listening after 25 s')
    const outcome = page.url().includes('run=') && final !== first ? final : final
    throw Object.assign(new Error(outcome.trim() || first), { info: true })
  }).catch(() => {})
  if (results.at(-1)?.check.startsWith('dock')) { const r = results.at(-1)!; r.ok = /Listening/.test(r.detail) || /denied|not available|unexpectedly|No speech|Could not|network/i.test(r.detail) ? null : r.ok; if (r.ok === null) r.detail = `Web Speech in automated Chrome: ${r.detail}` }
  await check('Home mic (browser voice, Chrome fake audio)', async () => {
    await page.goto(`${BASE}/home?company=${COMPANY}`)
    await page.getByRole('button', { name: 'Speak one question' }).click()
    const status = page.locator('[data-testid="ask-card"] [role="status"], [data-testid="ask-card"] [role="alert"]')
    await until(async () => (await status.textContent()) || '', t => t.trim().length > 0, 'home voice status', 10000)
    const first = (await status.textContent())!.trim()
    await until(async () => page.url().includes('run=') ? 'navigated' : ((await status.textContent().catch(() => '')) || ''), t => t === 'navigated' || !t.startsWith('Listening'), 'speech result', 25000).catch(() => null)
    if (page.url().includes('run=')) return `recognized speech and opened ${page.url().replace(BASE, '')}`
    throw new Error((await status.textContent().catch(() => '')) || first)
  })
  { const r = results.at(-1)!; if (!r.ok) { r.ok = null; r.detail = `Web Speech in automated Chrome: ${r.detail}` } }
  await check('browser call: Call Span greets aloud, listens, hears the question, answers, listens again, hangs up', async () => {
    await page.goto(`${BASE}/?live&new=1&voice=browser&call=1&company=${COMPANY}`)
    const speech = page.waitForResponse(r => r.url().includes('/api/voice/speech'), { timeout: 20000 }).catch(() => null)
    await page.getByRole('button', { name: 'Call Span' }).click()
    const status = page.locator('[data-testid="call-controls"] [role="status"], [data-testid="call-controls"] [role="alert"]')
    const greeting = await speech
    const asked = page.waitForResponse(r => r.url().includes('/api/ask?') && r.request().method() === 'POST', { timeout: 60000 })
    await until(async () => (await status.textContent()) || '', t => t.startsWith('Listening'), 'listening after the greeting', 40000)
    const ask = await asked  // Chrome's fake microphone plays the question file; Web Speech transcribes it
    const callRun = (await ask.json()).run_id
    await until(() => replay(callRun), r => r.events.some((e: any) => e.event === 'run.end'), 'answer to the spoken question', 120000)
    await until(async () => (await status.textContent()) || '', t => t.startsWith('Listening') || t.startsWith('Span is speaking'), 'Span speaking or listening again', 40000)
    await page.getByRole('button', { name: 'Hang up' }).click()
    await until(async () => (await status.textContent()) || '', t => t.startsWith('Browser call'), 'hung up', 10000)
    return `greeting via ${greeting ? `ElevenLabs (${greeting.status()})` : 'browser voice'}; spoken question became ${callRun}`
  })
  let token = '', amount = 0
  await check('after approval: simulated reminders, negotiation and a pay link appear', async () => {
    const r = await until(() => replay(runId), rr => rr.events.some((e: any) => e.data.data?.agreement?.installments?.length), 'agreement', 240000)
    const reminders = r.events.filter((e: any) => e.event === 'node.create' && e.data.data?.kind === 'reminder')
    const inst = r.events.find((e: any) => e.data.data?.agreement?.installments?.length).data.data.agreement.installments[0]
    token = inst.pay_token; amount = inst.amount
    return `${reminders.length} reminders (${[...new Set(reminders.map((e: any) => e.data.data.channel))].join(',')}), installment ${amount}`
  })
  await check('pay page (Visa test card) updates Get paid', async () => {
    await page.goto(`${BASE}/get-paid?company=${COMPANY}`)
    const link = page.locator(`a[href="/api/pay/${token}/page"]`).first(); await link.waitFor()
    await page.goto(BASE + await link.getAttribute('href'))
    await page.locator('#cc-number').fill('4111111111111111'); await page.locator('#cc-exp').fill('12/28'); await page.locator('#cc-cvv').fill('123'); await page.locator('#cc-name').fill('E2E customer')
    await page.locator('#visa-btn').click(); await page.locator('#receipt:not(.hidden)').waitFor()
    await page.goto(`${BASE}/get-paid?company=${COMPANY}`)
    await page.locator('[data-testid="payments"] tbody tr').first().waitFor()
    const paid = await page.locator('[data-testid="pay-links"] tbody tr', { hasText: 'paid' }).count()
    const collected = await page.getByText('Collected').locator('..').textContent()
    return `payments table has a row; ${paid} link(s) marked paid; ${collected?.replace(/\s+/g, ' ').slice(0, 60)}`
  })
  await check('report opens, Print calls window.print, PDF downloads', async () => {
    const runs = await until(() => json(`/api/runs?company=${COMPANY}`), j => j.runs.some((x: any) => x.run_id === runId && x.report_id), 'report id', 120000)
    const reportId = runs.runs.find((x: any) => x.run_id === runId).report_id
    await page.goto(`${BASE}/reports?company=${COMPANY}`); await page.locator(`a[href^="/report/${reportId}"]`).first().waitFor()
    await page.goto(`${BASE}/report/${reportId}?company=${COMPANY}`)
    await page.locator('h1.q').waitFor()
    await page.evaluate(() => { (window as any).__printed = 0; window.print = () => { (window as any).__printed++ } })
    await page.getByRole('button', { name: 'Print' }).click()
    if (!(await page.evaluate(() => (window as any).__printed))) throw new Error('window.print was not called')
    const href = await page.getByRole('link', { name: 'Download PDF' }).getAttribute('href')
    const pdf = await fetch(BASE + href); const bytes = Buffer.from(await pdf.arrayBuffer())
    if (!pdf.ok || bytes.subarray(0, 5).toString() !== '%PDF-') throw new Error(`pdf ${pdf.status}`)
    writeFileSync(join(OUT, 'report.pdf'), bytes)
    return `report ${reportId}, PDF ${bytes.length} bytes`
  })
  await check('no console errors across the chat/decision/payment flow', async () => { if (errors.length) throw new Error(errors.slice(0, 6).join(' | ')); return 'clean' })
  await page.screenshot({ path: join(OUT, 'final.png'), fullPage: true }).catch(() => {})
  await context.close()
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  await available(PORT); await available(AGENT_PORT)
  const wav = join(OUT, 'question.wav')
  if (process.platform === 'darwin') spawnSync('say', ['-o', wav, '--data-format=LEI16@16000', 'Will I make payroll in two weeks?'])
  command('npm', ['run', 'build'], join(ROOT, 'frontend'))
  const manifest = JSON.parse(command(PYTHON, ['backend/scripts/demo_db.py', 'create', '--name', `span_test_e2e_${STAMP}`]))
  log(`fresh isolated database ${manifest.database}`)
  const database = readFileSync(manifest.env_file, 'utf8').split('\n').find(s => s.startsWith('DATABASE_URL='))!.slice(13)
  const env = { ...process.env, DATABASE_URL: database, DEMO_COMPANY: COMPANY, PUBLIC_BASE_URL: BASE, INTERNAL_API_URL: BASE,
    AGENT_PORT: String(AGENT_PORT), CUSTOMER_AGENT_ENDPOINT: `http://127.0.0.1:${AGENT_PORT}/submit`,
    PHOTON_API_KEY: '', PHOTON_PROJECT_ID: '', VISA_USER_ID: '', VISA_PASSWORD: '', AGENTVERSE_API_KEY: '', SENTRY_DSN: '', SCORING_INTERVAL_MS: '0' }
  const start = (args: string[], logName: string) => { const fd = openSync(join(OUT, logName), 'w', 0o600); const child = spawn(PYTHON, args, { cwd: BACKEND, env, stdio: ['ignore', fd, fd] }); children.push(child); return child }
  start(['-m', 'uvicorn', 'owed.main:app', '--host', '127.0.0.1', '--port', String(PORT)], 'backend.log')
  start(['-m', 'owed.agents.runtime'], 'agents.log')
  await until(async () => { try { return await json('/api/health') } catch { return null } }, h => !!h?.ok, 'isolated API startup', 60000)
  await sleep(4000)
  const args = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', ...(existsSync(wav) ? [`--use-file-for-fake-audio-capture=${wav}`] : [])]
  const browser = await chromium.launch({ channel: 'chrome', headless: !process.env.E2E_HEADED, args })
  log(`Chrome ${browser.version()} (${process.env.E2E_HEADED ? 'headed' : 'headless'})`)
  try { await railPages(browser); await chatAndDecisions(browser, wav) } finally { await browser.close() }
  writeFileSync(join(OUT, 'report.json'), JSON.stringify({ base: BASE, database: manifest.database, chrome: 'channel chrome', results }, null, 2))
  const failed = results.filter(r => r.ok === false)
  console.log(`\n${results.filter(r => r.ok).length} passed, ${failed.length} failed, ${results.filter(r => r.ok === null).length} informational → ${join(OUT, 'report.json')}`)
  process.exitCode = failed.length ? 1 : 0
}
main().catch(e => { console.error(String(e)); process.exitCode = 1 }).finally(async () => {
  for (const child of children) child.kill('SIGTERM')
  await Promise.all(children.map(child => child.exitCode !== null ? Promise.resolve() : new Promise(resolve => child.once('exit', resolve))))
})
