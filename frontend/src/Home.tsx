import { useEffect, useRef, useState } from 'react'
import { getBrief, getCash, getCashHistory, getCompanies, getRuns, startRun } from './api'
import { coverageSeries, type HistoryPoint } from './forecastTrend'
import type { Brief, CashProjection, Company, RunSummary } from './types'
import { money as moneyPos } from './events'
import { listenOnce, type VoiceStatus } from './browserVoice'
import { PaymentHeatmap } from './PaymentHeatmap'

/** `money` from events.ts renders negatives as "$-7,457"; the home page shows a proper minus sign. */
const money = (v?: number) => v != null && v < 0 ? `−${moneyPos(-v)}` : moneyPos(v)

const BRAND = (import.meta.env.VITE_BRAND as string) || 'Span'
const DEFAULT_COMPANY = 'company-020'
const SUGGESTIONS = ['Am I going to make payroll these next two weeks?', 'Should I take Gallagher’s order?', 'Who should I chase today?']

const I = {
  book: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="4" width="11" height="8.5" rx="1"/><path d="M2.5 7h11"/></svg>,
  people: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="6" cy="5.5" r="2.5"/><path d="M1.5 13c.8-3 2.6-4 4.5-4s3.7 1 4.5 4M11 6l1.3 1.3L14.5 5"/></svg>,
  trend: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2.5 12.5 6 8l3 2.5 4.5-6"/></svg>,
  chat: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/></svg>,
  cal: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="3.5" width="11" height="10" rx="1"/><path d="M2.5 7h11M5.5 2v3M10.5 2v3"/></svg>,
  person: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 14c.8-3 2.6-4 5-4s4.2 1 5 4"/></svg>,
  card: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M2 7.5h12M5 11h3"/></svg>,
  bank: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2 6.5 8 3l6 3.5M3.5 7v5M8 7v5M12.5 7v5M2 13.5h12"/></svg>,
  mic: <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="5.5" y="1.5" width="5" height="8" rx="2.5"/><path d="M3 7.5a5 5 0 0 0 10 0M8 12.5v2"/></svg>,
  phone: <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3.5 2.5h2.5l1.2 3-1.6 1a8 8 0 0 0 4 4l1-1.6 3 1.2v2.5a1.5 1.5 0 0 1-1.6 1.5A11.5 11.5 0 0 1 2 4.1 1.5 1.5 0 0 1 3.5 2.5z"/></svg>,
  arrow: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5"/></svg>,
}

const greeting = (d = new Date()) => { const h = d.getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }
const fmtLong = (d: Date) => d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
const fmtDay = (s?: string | null) => s ? new Date(s + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '—'
const fmtShort = (s?: string | null) => s ? new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'
const ago = (s: string) => {
  const ms = Date.now() - new Date(s).getTime(); const m = Math.round(ms / 60000)
  if (!isFinite(m)) return ''
  if (m < 1) return 'just now'; if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60); if (h < 24) return `${h} h ago`
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
/** Verdict color from the answer title: green / amber / red, grey while open or unknown. */
export const verdictTone = (title?: string | null): 'green' | 'amber' | 'red' | 'grey' => {
  const t = (title || '').trim().toLowerCase()
  if (!t) return 'grey'
  if (/^(yes|covered|on track|take it|go ahead)/.test(t)) return 'green'
  if (/^(barely|tight|close|maybe|probably)/.test(t)) return 'amber'
  if (/^(no|short|not )/.test(t)) return 'red'
  return 'grey'
}
const sourceLabel = (s: string) => s === 'call' ? 'by phone' : s === 'sms' ? 'by text' : s === 'asi_one' ? 'via ASI:One' : 'on the web'

/** Send the owner to the canvas: `/?run=<id>` replays a run and keeps listening for new events. */
const canvasUrl = (runId: string, company: string, browserVoice = false) =>
  `/?run=${encodeURIComponent(runId)}${company !== DEFAULT_COMPANY ? `&company=${encodeURIComponent(company)}` : ''}${browserVoice ? '&voice=browser' : ''}`

function Tile({ icon, cls, label, value, sub, loading }: { icon: React.ReactNode; cls: string; label: string; value?: string; sub?: string; loading?: boolean }) {
  return <div className="card tile">
    <div className="tl"><span className={`ic ${cls}`}>{icon}</span>{label}</div>
    {loading ? <div className="thinking" style={{ marginTop: 10 }}><i/><i/><i/></div> : <>
      <div className="tv">{value ?? '—'}</div>
      <div className="fine">{sub || '\u00a0'}</div>
    </>}
  </div>
}

function Sparkline({ cash }: { cash: CashProjection }) {
  const W = 560, H = 150, top = 12, bottom = 126
  const all = [...cash.days, ...cash.pessimistic_days].map(d => d.balance)
  const lo = Math.min(0, ...all), hi = Math.max(1, ...all)
  const y = (v: number) => bottom - (v - lo) / (hi - lo) * (bottom - top)
  const x = (i: number) => 6 + i / Math.max(1, cash.days.length - 1) * (W - 12)
  const path = (days: CashProjection['days']) => days.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(d.balance).toFixed(1)}`).join(' ')
  const lowI = cash.days.findIndex(d => d.date === cash.low_point.date)
  const end = cash.days.at(-1)
  return <svg viewBox={`0 0 ${W} ${H}`} fill="none" role="img" aria-label="Projected cash for the next 14 days" style={{ width: '100%', height: 'auto', display: 'block' }}>
    <path d={`${path(cash.days)} L${x(cash.days.length - 1)} ${y(lo)} L${x(0)} ${y(lo)} Z`} fill="#2CA01C" fillOpacity=".08" />
    <path d={`M0 ${y(0)} H${W}`} stroke="#D52B1E" strokeWidth="1" strokeDasharray="4 4" />
    {cash.payroll_dates.map(day => { const i = cash.days.findIndex(d => d.date === day); return i < 0 ? null : <path key={day} d={`M${x(i)} ${top} V${bottom}`} stroke="#8D9096" strokeDasharray="2 4"><title>{day}: payroll</title></path> })}
    <path d={path(cash.pessimistic_days)} stroke="#E08A00" strokeWidth="1.5" strokeDasharray="4 3" />
    <path d={path(cash.days)} stroke="#2CA01C" strokeWidth="2.5" strokeLinejoin="round" />
    {lowI >= 0 && <circle cx={x(lowI)} cy={y(cash.low_point.balance)} r="4" fill="#fff" stroke={cash.low_point.balance < 0 ? '#D52B1E' : '#E08A00'} strokeWidth="2"><title>Low point {cash.low_point.date}: {money(cash.low_point.balance)}</title></circle>}
    {end && <circle cx={x(cash.days.length - 1)} cy={y(end.balance)} r="4" fill="#2CA01C" />}
    <text x="6" y={H - 4} fontSize="11" fill="#6B6C72">{fmtDay(cash.start)} · {money(cash.opening_balance)}</text>
    <text x={W - 6} y={H - 4} fontSize="11" fill="#393A3D" fontWeight="600" textAnchor="end">{fmtDay(cash.target)} · {money(end?.balance)}</text>
  </svg>
}

/** Forecast over time: every saved payroll forecast (cash_projection hypertable), newest on the right. */
function ForecastTrend({ company }: { company: string }) {
  const [state, setState] = useState<{ company: string; points?: HistoryPoint[]; error?: string }>({ company })
  useEffect(() => {
    let on = true
    setState({ company })
    getCashHistory(company).then(r => { if (on) setState({ company, points: r.points }) }).catch(e => { if (on) setState({ company, error: String(e.message || e) }) })
    return () => { on = false }
  }, [company])
  const series = coverageSeries(state.company === company && state.points ? state.points : [])
  const W = 560, H = 110, top = 12, bottom = 86
  const y = (v: number) => bottom - (v - series.low) / Math.max(1, series.high - series.low) * (bottom - top)
  const x = (i: number) => 8 + i / Math.max(1, series.points.length - 1) * (W - 16)
  const path = series.points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.coverage).toFixed(1)}`).join(' ')
  const last = series.points.at(-1)
  return <section className="card spark trend" data-testid="forecast-trend">
    <div className="head"><b>Forecast over time</b>
      {series.latest && <span className="fine">latest: {series.latest.coverage < 0 ? `${money(series.latest.coverage)} short` : `${money(series.latest.coverage)} to spare`} on {fmtDay(series.latest.target)}</span>}
    </div>
    {state.error ? <div className="fine" role="alert" style={{ color: 'var(--red)' }}>Forecast history unavailable: {state.error}</div>
      : !state.points ? <div className="thinking" style={{ height: 60 }}><i/><i/><i/> loading</div>
      : series.points.length === 0 ? <div className="fine">No saved forecasts yet. Ask about payroll and each forecast is kept here.</div>
      : <svg viewBox={`0 0 ${W} ${H}`} fill="none" role="img" aria-label="Payroll coverage across saved forecasts" style={{ width: '100%', height: 'auto', display: 'block' }}>
        <path d={`M0 ${y(0)} H${W}`} stroke="#8D9096" strokeWidth="1" strokeDasharray="4 4" />
        <path d={path} stroke="#2CA01C" strokeWidth="2" strokeLinejoin="round" />
        {series.points.map((p, i) => <circle key={p.forecast_id} cx={x(i)} cy={y(p.coverage)} r="3.5" fill={p.coverage < 0 ? '#D52B1E' : '#2CA01C'}><title>{new Date(p.computed_at).toLocaleString()} · {p.label} · {money(p.coverage)}</title></circle>)}
        <text x="8" y={H - 4} fontSize="11" fill="#6B6C72">{series.points.length} saved forecast{series.points.length === 1 ? '' : 's'} · TimescaleDB hypertable</text>
        {last && <text x={W - 8} y={H - 4} fontSize="11" fill="#393A3D" fontWeight="600" textAnchor="end">{money(last.coverage)}</text>}
      </svg>}
  </section>
}

export default function Home() {
  const [company, setCompany] = useState(new URLSearchParams(location.search).get('company') || DEFAULT_COMPANY)
  const [companies, setCompanies] = useState<Company[]>([])
  const [brief, setBrief] = useState<Brief | null>(null)
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [cash, setCash] = useState<CashProjection | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [q, setQ] = useState('')
  const [asking, setAsking] = useState<string | null>(null)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle')
  const [voiceMessage, setVoiceMessage] = useState('')
  const stopListening = useRef<() => void>(() => {})
  const fail = (key: string) => (e: unknown) => setErrors(prev => ({ ...prev, [key]: e instanceof Error ? e.message : String(e) }))
  const clear = (key: string) => setErrors(prev => { const { [key]: _drop, ...rest } = prev; return rest })

  useEffect(() => { getCompanies().then(setCompanies).catch(fail('companies')) }, [])
  useEffect(() => {
    let stale = false
    setBrief(null); setRuns(null); setCash(null); setErrors({})
    const briefReq = getBrief(company)
    briefReq.then(b => { if (!stale) { setBrief(b); clear('brief') } }).catch(e => !stale && fail('brief')(e))
    getRuns(company).then(r => { if (!stale) { setRuns(r); clear('runs') } }).catch(e => !stale && fail('runs')(e))
    briefReq.then(b => {
      const t = new Date(b.as_of + 'T00:00:00'); t.setDate(t.getDate() + 14)
      return getCash(company, t.toISOString().slice(0, 10))
    }).then(c => { if (!stale) { setCash(c); clear('cash') } }).catch(e => !stale && fail('cash')(e))
    return () => { stale = true }
  }, [company])

  useEffect(() => () => stopListening.current(), [])

  const ask = async (question: string, source = 'web', browserVoice = false) => {
    const text = question.trim(); if (!text || asking) return
    setAsking(text); clear('ask')
    try { const { run_id } = await startRun(company, text, source); location.href = canvasUrl(run_id, company, browserVoice) }
    catch (e) { fail('ask')(e); setAsking(null) }
  }
  const startVoiceQuestion = () => {
    setVoiceMessage('')
    stopListening.current()
    stopListening.current = listenOnce(
      text => { stopListening.current(); setVoiceStatus('idle'); void ask(text, 'call', true) },
      (status, message) => { setVoiceStatus(status); setVoiceMessage(message || '') },
    )
  }

  const name = brief?.company.name || companies.find(c => c.id === company)?.name || 'Loading…'
  const recent = (runs || []).filter(r => !r.parent_run_id).slice(0, 8)
  return <div className="app">
    <header className="topbar">
      <div className="brand"><img className="mark" src="/logo.png" alt="" /><div className="name">{BRAND.toLowerCase()}</div></div>
      <div className="company">{name}</div>
      <div className="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg><input placeholder="Ask about your money, or search transactions, customers, reports" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') ask(q) }} /></div>
      <div className="status"><i className="dot" />Books as of {fmtShort(brief?.as_of)}</div>
    </header>
    <div className="body">
      <nav className="rail">
        <a href="/">{I.chat}Ask</a><a className="on" href="/home">{I.book}Home</a><a href={`/get-paid${company !== DEFAULT_COMPANY ? `?company=${encodeURIComponent(company)}` : ''}`}>{I.card}Get paid</a><a href={`/reports${company !== DEFAULT_COMPANY ? `?company=${encodeURIComponent(company)}` : ''}`}>{I.trend}Reports</a><a href={`/customers${company !== DEFAULT_COMPANY ? `?company=${encodeURIComponent(company)}` : ''}`}>{I.person}Customers</a>
      </nav>
      <main className="main home" data-testid="home">
        <div className="hhead">
          <div>
            <h1 className="q" style={{ marginBottom: 4, paddingRight: 0 }}>{greeting()}, Ryan</h1>
            <div className="eyebrow" style={{ marginBottom: 0 }}><span style={{ whiteSpace: 'nowrap' }}>{fmtLong(new Date())}</span><span className="sep" /><span>{brief ? brief.headline : errors.brief ? 'Couldn’t load today’s picture.' : 'Reading the books…'}</span></div>
          </div>
          <label className="switcher">
            <span className="fine">Company</span>
            <select value={company} onChange={e => { setCompany(e.target.value); history.replaceState(null, '', e.target.value === DEFAULT_COMPANY ? '/home' : `/home?company=${e.target.value}`) }} aria-label="Company">
              {companies.length === 0 && <option value={company}>{name}</option>}
              {companies.map(c => <option key={c.id} value={c.id}>{c.name}{c.distressed ? ' · distressed' : ''}</option>)}
            </select>
          </label>
        </div>
        {errors.brief && <div className="card err" role="alert">Today’s numbers didn’t load: {errors.brief} <button className="btn" style={{ height: 28, marginLeft: 8 }} onClick={() => setCompany(c => c)}>Retry</button></div>}

        <div className="tiles">
          <Tile icon={I.bank} cls="blue" label="In the bank" loading={!brief && !errors.brief} value={brief ? money(brief.bank_balance) : undefined} sub={brief ? `as of ${fmtDay(brief.as_of)}` : undefined} />
          <Tile icon={I.people} cls="green" label="Owed to you" loading={!brief && !errors.brief} value={brief ? money(brief.owed_total) : undefined} sub={brief ? `${brief.open_invoices} open invoices · ${money(brief.overdue_total)} overdue` : undefined} />
          <Tile icon={I.cal} cls="dark" label="Payroll next" loading={!brief && !errors.brief} value={brief ? (brief.payroll_next ? money(brief.payroll_next.amount) : 'None due') : undefined} sub={brief?.payroll_next ? `${fmtDay(brief.payroll_next.date)} · ${brief.payroll_next.headcount} people` : brief ? 'no run in the next week' : undefined} />
          <Tile icon={I.card} cls="amber" label="Bills due this week" loading={!brief && !errors.brief} value={brief ? money(brief.bills_due_week.total) : undefined} sub={brief ? `${brief.bills_due_week.count} bill${brief.bills_due_week.count === 1 ? '' : 's'} through ${fmtDay(brief.bills_due_week.through)}` : undefined} />
        </div>

        <PaymentHeatmap company={company} limit={12} compact />

        <div className="hgrid">
          <section className="card ask" data-testid="ask-card">
            <h2>Ask {BRAND}</h2>
            <div className="fine">Type it, or try browser voice. {BRAND} reasons on the canvas and acts when you say yes. Browser voice is a turn-based demo, not a phone call.</div>
            <div className="big-input">
              <input autoFocus placeholder={`What do you want to know about your money?`} value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') ask(q) }} disabled={!!asking} />
              <button className={`mic ${voiceStatus === 'listening' ? 'listening' : ''}`} type="button" title="Speak one question" aria-label={voiceStatus === 'listening' ? 'Listening for one question' : 'Speak one question'} aria-pressed={voiceStatus === 'listening'} disabled={!!asking || voiceStatus === 'listening'} onClick={startVoiceQuestion}>{I.mic}</button>
              <button className="btn primary" onClick={() => ask(q)} disabled={!q.trim() || !!asking}>{asking ? 'Starting…' : 'Ask'}</button>
            </div>
            <div className="fine" role={voiceStatus === 'error' ? 'alert' : 'status'} aria-live="polite">{voiceStatus === 'listening' ? 'Listening… Speak one question.' : voiceMessage}</div>
            <div className="sugg" style={{ marginTop: 12 }}>
              {SUGGESTIONS.map(s => <button key={s} onClick={() => ask(s)} disabled={!!asking}>{asking === s ? 'Starting…' : s}</button>)}
            </div>
            {errors.ask && <div className="fine" role="alert" style={{ color: 'var(--red)', marginTop: 8 }}>{errors.ask}</div>}
          </section>

          <section className="card spark" data-testid="cash-sparkline">
            <div className="head"><b>Next 14 days</b>
              {cash && <span className="fine">low {money(cash.low_point.balance)} on {fmtDay(cash.low_point.date)}</span>}
            </div>
            {cash ? <Sparkline cash={cash} />
              : errors.cash ? <div className="fine" role="alert" style={{ color: 'var(--red)' }}>Cash projection unavailable: {errors.cash}</div>
              : <div className="thinking" style={{ height: 96 }}><i/><i/><i/> projecting</div>}
            <div className="legend"><span><i style={{ width: 14, height: 3, borderRadius: 2, background: 'var(--green)' }} />expected</span><span><i style={{ width: 14, height: 0, borderTop: '2px dashed var(--amber)', borderRadius: 0 }} />if slow payers slip</span><span><i style={{ width: 14, height: 0, borderTop: '2px dashed var(--red)', borderRadius: 0 }} />zero</span></div>
          </section>
        </div>

        <ForecastTrend company={company} />

        <section className="card threads" data-testid="recent-threads">
          <div className="head"><b>Recent threads</b><span className="fine">{recent.length ? `${recent.length} of ${(runs || []).length}` : ''}</span></div>
          {runs === null && !errors.runs && <div className="thinking"><i/><i/><i/> loading</div>}
          {errors.runs && <div className="fine" role="alert" style={{ color: 'var(--red)' }}>Couldn’t load threads: {errors.runs}</div>}
          {runs && recent.length === 0 && <div className="fine">Nothing asked yet. Try a question above.</div>}
          {recent.map(r => {
            const tone = verdictTone(r.answer_title)
            return <a key={r.run_id} className="thread-row" href={canvasUrl(r.run_id, company)}>
              <span className={`ic ${r.source === 'call' ? 'green' : 'grey'}`} style={{ width: 22, height: 22 }}>{r.source === 'call' ? I.phone : I.chat}</span>
              <span className="tq">{r.question}</span>
              <span className={`pill-v ${tone}`}>{r.answer_title || (r.status === 'open' ? 'In progress' : 'No answer')}</span>
              <span className="fine when">{sourceLabel(r.source)} · {ago(r.started_at)}</span>
              <span className="go">{I.arrow}</span>
            </a>
          })}
        </section>
      </main>
    </div>
  </div>
}
