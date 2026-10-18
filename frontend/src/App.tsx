import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type React from 'react'
import type { Decision, GraphNode, Lever, RawEvent, RunState } from './types'
import { emptyRun, k, money, plain, reduce } from './events'
import { generateReport, playFixture, resolveDecision, startRun } from './api'
import ForecastHistory from './ForecastHistory'
import ChatSidebar from './ChatSidebar'
import { readChatTitle, writeChatTitle } from './chatHistory'
import DailyCashChart from './DailyCashChart'
import { connectLive } from './live'
import { approvalChoice, assistantSpeechText, claimSpeechEvent, listenOnce, type VoiceStatus } from './browserVoice'

const PARAMS = new URLSearchParams(location.search)
const COMPANY = PARAMS.get('company') || 'company-020'
const BRAND = (import.meta.env.VITE_BRAND as string) || 'Span'
const LIVE = new URLSearchParams(location.search).has('live') || new URLSearchParams(location.search).has('run')
const SPEED = Number(new URLSearchParams(location.search).get('speed') || 1)
const RUN = new URLSearchParams(location.search).get('run')
const FRESH = PARAMS.has('new')
const STATIC = new URLSearchParams(location.search).has('static')
const BROWSER_VOICE = PARAMS.get('voice') === 'browser'

/* ---------- icons ---------- */
const I = {
  book: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="4" width="11" height="8.5" rx="1"/><path d="M2.5 7h11"/></svg>,
  people: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="6" cy="5.5" r="2.5"/><path d="M1.5 13c.8-3 2.6-4 4.5-4s3.7 1 4.5 4M11 6l1.3 1.3L14.5 5"/></svg>,
  trend: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2.5 12.5 6 8l3 2.5 4.5-6"/></svg>,
  chat: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/></svg>,
  cal: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="3.5" width="11" height="10" rx="1"/><path d="M2.5 7h11M5.5 2v3M10.5 2v3"/></svg>,
  person: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 14c.8-3 2.6-4 5-4s4.2 1 5 4"/></svg>,
  phone: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3.5 2.5h2.5l1.2 3-1.6 1a8 8 0 0 0 4 4l1-1.6 3 1.2v2.5a1.5 1.5 0 0 1-1.6 1.5A11.5 11.5 0 0 1 2 4.1 1.5 1.5 0 0 1 3.5 2.5z"/></svg>,
  mic: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="5.5" y="1.5" width="5" height="8" rx="2.5"/><path d="M3 7.5a5 5 0 0 0 10 0M8 12.5v2"/></svg>,
  check: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 8.5l3 3 7-7"/></svg>,
  star: <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5l1.6 4.1 4.4.3-3.4 2.8 1.1 4.3L8 10.6 4.3 13l1.1-4.3L2 5.9l4.4-.3z"/></svg>,
  arrow: <svg width="24" height="12" viewBox="0 0 24 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M0 6h20M16 2l4 4-4 4"/></svg>,
  card: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M2 7.5h12M5 11h3"/></svg>,
}
const AV_COLORS = ['#0077C5', '#7A5AF8', '#E08A00', '#2CA01C', '#D52B1E']
const initials = (s: string) => s.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase()
const fmtDate = (s?: string) => s ? new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''

/* ---------- nodes ---------- */
function BooksNode({ n }: { n: GraphNode }) {
  const d = n.data; const bank = d.bank_balance, pay = d.payroll_due_by_target ?? d.payroll_amount, bills = d.bills_due_by_target
  const max = Math.max(bank || 0, pay || 0, bills || 0, 1)
  const Row = ({ l, v, c }: { l: string; v?: number; c: string }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><div className="kv"><span style={{ color: 'var(--muted)' }}>{l}</span><b>${k(v)}</b></div><div className="bar"><i style={{ width: `${100 * (v || 0) / max}%`, background: c }} /></div></div>)
  return <div className={`node ${n.status}`} style={{ width: 270 }}>
    <h3><span className="ic blue">{I.book}</span>Your books</h3>
    {n.status === 'running' && !bank ? <div className="thinking"><i/><i/><i/> reading</div> : <>
      <Row l="In the bank" v={bank} c="var(--blue)" />
      <Row l={`Payroll${d.headcount ? ` · ${d.headcount} people` : ''}`} v={pay} c="var(--text)" />
      {bills != null && <Row l="Bills due" v={bills} c="var(--muted2)" />}
      <div className="fine">through {fmtDate(d.target_date || d.payroll_date)}</div></>}
  </div>
}
function ScoredNode({ n }: { n: GraphNode }) {
  const total = n.progress?.total || n.rows.length || 0
  const sample = n.rows.filter((_, i) => i % Math.max(1, Math.floor(n.rows.length / 72)) === 0).slice(0, 72)
  const likely = n.rows.reduce((a, r) => a + r.amount * r.p_paid_by_target, 0), owed = n.rows.reduce((a, r) => a + r.amount, 0)
  const col = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' }
  return <div className={`node ${n.status}`} style={{ width: 330 }}>
    <h3><span className="ic green">{I.people}</span>{total || '…'} invoices scored{n.status === 'running' && n.progress ? <span className="fine" style={{ marginLeft: 'auto' }}>{n.progress.done} / {n.progress.total}</span> : null}</h3>
    <div className="dots">{sample.map(r => <i key={r.invoice_id} style={{ background: col[r.band] || col.amber }} title={`${r.customer} · $${Math.round(r.amount)} · ${Math.round(r.p_paid_by_target * 100)}%`} />)}</div>
    <div className="legend"><span><i style={{ background: 'var(--green)' }} />will pay</span><span><i style={{ background: 'var(--amber)' }} />maybe</span><span><i style={{ background: 'var(--red)' }} />unlikely</span></div>
    {n.data.overdue_only && <div style={{ maxHeight: 280, overflow: 'auto' }}>{n.rows.map(r => <div className="kv" key={r.invoice_id}><span>{r.customer}</span><b>{r.days_past_due}d · {money(r.amount)}</b></div>)}</div>}
    {n.rows.length > 0 && <div className="kv"><span style={{ color: 'var(--muted)' }}>Likely in time</span><b>${k(likely)} of ${k(owed)}</b></div>}
  </div>
}
function CashNode({ n, ctx }: { n: GraphNode; ctx?: GraphNode }) {
  const d = n.data; const bank = d.bank_balance ?? ctx?.data.bank_balance ?? 0, inn = bank + (d.expected_by_target || 0)
  const pay = d.payroll_due_by_target ?? ctx?.data.payroll_due_by_target ?? ctx?.data.payroll_amount ?? 0, bills = d.bills_due_by_target ?? ctx?.data.bills_due_by_target ?? 0
  const out = pay + bills + (d.owner_draw_by_target || 0); const max = Math.max(inn, out, 1)
  return <div className={`node ${n.status}`} style={{ width: 330 }}>
    <h3><span className="ic dark">{I.trend}</span>Cash on {fmtDate(d.target_date || ctx?.data.target_date || ctx?.data.payroll_date)}</h3>
    {n.status === 'running' && !d.expected_by_target ? <div className="thinking"><i/><i/><i/> forecasting</div> : <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="kv"><span style={{ color: 'var(--muted)' }}>Coming in</span><b>${k(inn)}</b></div>
        <div className="bar tall"><i style={{ width: `${100 * bank / max}%`, background: 'var(--blue)' }} /><i style={{ width: `${100 * (inn - bank) / max}%`, background: 'var(--green)' }} /></div>
        <div className="legend sq"><span><i style={{ background: 'var(--blue)' }} />bank</span><span><i style={{ background: 'var(--green)' }} />likely payments</span></div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="kv"><span style={{ color: 'var(--muted)' }}>Going out</span><b>${k(out)}</b></div>
        <div className="bar tall"><i style={{ width: `${100 * pay / max}%`, background: 'var(--text)' }} /><i style={{ width: `${100 * (out - pay) / max}%`, background: 'var(--muted2)' }} /></div>
        <div className="legend sq"><span><i style={{ background: 'var(--text)' }} />payroll</span><span><i style={{ background: 'var(--muted2)' }} />bills</span></div>
      </div></>}
  </div>
}
function Gauge({ cushion, need }: { cushion: number; need: number }) {
  const ratio = Math.max(-1, Math.min(1, cushion / Math.max(need * 0.25, 1)))
  const deg = ratio * 80
  return <svg width="150" height="84" viewBox="0 0 150 84" fill="none">
    <path d="M12 78 A63 63 0 0 1 48 23" stroke="#D52B1E" strokeWidth="12" strokeLinecap="round" />
    <path d="M52 21 A63 63 0 0 1 98 21" stroke="#E08A00" strokeWidth="12" strokeLinecap="round" />
    <path d="M102 23 A63 63 0 0 1 138 78" stroke="#2CA01C" strokeWidth="12" strokeLinecap="round" />
    <g className="needle" style={{ transform: `rotate(${deg}deg)` }}><path d="M75 78 L75 28" stroke="#393A3D" strokeWidth="3" strokeLinecap="round" /></g>
    <circle cx="75" cy="78" r="5" fill="#393A3D" />
  </svg>
}
function VerdictNode({ n, fc }: { n: GraphNode; fc?: GraphNode }) {
  const gap = fc?.data.gap ?? n.data.gap ?? 0; const need = fc?.data.need ?? 0
  const cushion = LIVE ? (fc?.data.cash_at_target ?? 0) - need : (fc?.data.cushion ?? (gap > 0 ? -gap : fc?.data.cash_at_target ?? 0))
  const risk = fc?.data.pessimistic?.gap
  const cls = cushion < 0 ? 'bad' : cushion < need * 0.1 ? '' : 'ok'
  const word = cushion < 0 ? 'No.' : cushion < need * 0.1 ? 'Barely.' : 'Yes.'
  return <div className={`node verdict ${cls}`}>
    <Gauge cushion={cushion} need={need} />
    <div className="big">{word}</div>
    <div className="sub">{cushion < 0 ? `${money(-cushion)} short` : `${money(cushion)} to spare`}</div>
    <div className="fine">{risk > 0 ? `${money(risk)} short if the slow payers slip` : cushion < 0 ? 'even if the usual payers pay' : 'covered even if the slow payers slip'}</div>
  </div>
}
function LeverCard({ l, rec, decision, onChoose, chosen }: { l: Lever; rec: boolean; decision?: Decision; onChoose: (opt: string, selected?: string[]) => void; chosen?: string }) {
  const icon = l.id === 'chase' ? I.chat : l.id === 'defer_bill' ? I.cal : I.person
  const zero = !l.recovers
  const primary = decision?.options.find(o => o.id === 'yes') || decision?.options[0]
  const [sel, setSel] = useState<Record<string, boolean>>({})
  const targets = l.targets || []
  const isOn = (id: string) => sel[id] !== false
  const picked = targets.filter(t => isOn(t.customer_id))
  const recovers = targets.length ? picked.reduce((a, t) => a + t.amount, 0) : l.recovers
  const label = targets.length && picked.length !== targets.length ? `Text ${picked.length} of ${targets.length} late payers` : l.label
  return <div className={`lever ${rec ? 'rec' : ''} ${zero ? 'dim' : ''}`}>
    <div>
      <div className="head"><b><span className={`ic ${rec ? 'green' : 'grey'}`}>{icon}</span>{label}</b><span className="amt" style={zero ? { color: 'var(--muted2)' } : undefined}>+ {money(recovers)}</span></div>
      {targets.length > 0 && <div className="chips" style={{ marginTop: 10 }}>{targets.map((t, i) => <button type="button" className={`chip pick ${isOn(t.customer_id) ? 'on' : 'off'}`} key={t.customer_id} disabled={!!chosen} onClick={() => setSel(x => ({ ...x, [t.customer_id]: !isOn(t.customer_id) }))} title={t.reason || t.customer}><span className="av" style={{ background: AV_COLORS[i % 5] }}>{initials(t.customer)}</span>{t.customer.split(' ')[0]} · {money(t.amount)}<span className="tick">{I.check}</span></button>)}</div>}
      {l.bills && <div className="chips" style={{ marginTop: 10 }}>{l.bills.map(b => <span className="chip plain" key={b.bill_id}>{b.vendor} · {money(b.amount)}</span>)}</div>}
      <div className="fine" style={{ marginTop: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
        {targets.length > 0 && <><i className="dot" />{chosen ? 'sent to the ones you picked' : 'tap a name to leave them out'}</>}
        {l.bills && <><i className="dot" />both have taken late payment before, no fee</>}
        {zero && 'Nothing scheduled this month, so nothing to hold.'}
      </div>
    </div>
    {rec && primary ? (
      chosen ? <button className="btn done" disabled>{I.check} {chosen === 'no' ? 'Not now' : `Texting ${picked.length}`}</button>
        : <div style={{ display: 'flex', gap: 8 }}><button className="btn primary" disabled={targets.length > 0 && picked.length === 0} onClick={() => onChoose(primary.id, picked.map(t => t.customer_id))}>{targets.length ? `Yes, text ${picked.length === targets.length ? 'them' : picked.length}` : primary.label}</button>{decision!.options.filter(o => o.id !== primary.id).slice(0, 1).map(o => <button key={o.id} className="btn" onClick={() => onChoose(o.id, picked.map(t => t.customer_id))}>{o.label}</button>)}</div>
    ) : rec ? <div className="thinking"><i/><i/><i/> weighing options</div>
      : zero ? <button className="btn ghost" disabled>Not needed</button> : <button className="btn">Add this too</button>}
  </div>
}
function Fork({ fromRef, toRefs, containerRef }: { fromRef: React.RefObject<HTMLDivElement | null>; toRefs: React.RefObject<HTMLDivElement | null>[]; containerRef: React.RefObject<HTMLDivElement | null> }) {
  const [geo, setGeo] = useState<{ w: number; from: number; to: number[] } | null>(null)
  useLayoutEffect(() => {
    const m = () => {
      const c = containerRef.current?.getBoundingClientRect(); const f = fromRef.current?.getBoundingClientRect(); if (!c || !f) return
      const to = toRefs.map(r => r.current?.getBoundingClientRect()).filter(Boolean).map(b => b!.left + b!.width / 2 - c.left)
      setGeo({ w: c.width, from: f.left + f.width / 2 - c.left, to })
    }
    m(); const ro = new ResizeObserver(m); if (containerRef.current) ro.observe(containerRef.current); window.addEventListener('resize', m)
    return () => { ro.disconnect(); window.removeEventListener('resize', m) }
  }, [fromRef, toRefs, containerRef])
  if (!geo || !geo.to.length) return <div className="fork" />
  const L = Math.min(...geo.to), R = Math.max(...geo.to, geo.from)
  return <svg className="fork" viewBox={`0 0 ${geo.w} 56`} preserveAspectRatio="none" fill="none" stroke="#8D9096" strokeWidth="1.5">
    <path d={`M${geo.from} 0 V14 Q${geo.from} 24 ${geo.from - 10} 24 H${L + 10} Q${L} 24 ${L} 34 V50 ${geo.to.map(x => `M${x} 24 V50`).join(' ')} M${L} 24 H${R}`} />
    {geo.to.map(x => <path key={x} d={`M${x - 5} 45l5 5 5-5`} />)}
  </svg>
}
function buildSeries(ctx?: GraphNode, sc?: GraphNode, fc?: GraphNode, received = 0) {
  if (!fc || fc.status !== 'done') { const bank = (ctx?.data.bank_balance ?? 0) + received; const days = 14; const flat = new Array(days + 1).fill(bank); return { good: flat, bad: flat, days, target: ctx?.data.target_date || ctx?.data.payroll_date, pay: ctx?.data.payroll_due_by_target ?? 0, bank, pending: true } }
  const bank = (ctx?.data.bank_balance ?? 0) + received
  const target = fc?.data.target_date || ctx?.data.target_date || ctx?.data.payroll_date
  const asOf = sc?.rows.length ? undefined : undefined; void asOf
  const days = 14
  const pay = ctx?.data.payroll_due_by_target ?? ctx?.data.payroll_amount ?? 0, bills = fc?.data.bills_due_by_target ?? ctx?.data.bills_due_by_target ?? 0
  const rows = sc?.rows || []
  const inflowGood = new Array(days + 1).fill(0), inflowBad = new Array(days + 1).fill(0)
  const expTotal = fc?.data.expected_by_target ?? rows.reduce((a, r) => a + r.amount * r.p_paid_by_target, 0)
  const rowSum = rows.reduce((a, r) => a + r.amount * r.p_paid_by_target, 0) || 1
  for (const r of rows) {
    const d = Math.min(days, Math.max(1, r.expected_days_to_pay || 7)); const v = r.amount * r.p_paid_by_target * (expTotal / rowSum)
    inflowGood[d] += v; if (r.p_paid_by_target >= 0.7) inflowBad[d] += v
  }
  if (!rows.length) for (let d = 1; d <= days; d++) { inflowGood[d] = expTotal / days; inflowBad[d] = expTotal * 0.82 / days }
  const out = new Array(days + 1).fill(0); out[Math.floor(days / 2)] += pay / 2; out[days] += pay / 2; out[3] += bills / 3; out[8] += bills / 3; out[12] += bills / 3
  const walk = (inf: number[]) => { let v = bank; const pts = [v]; for (let d = 1; d <= days; d++) { v += inf[d] - out[d]; pts.push(v) } return pts }
  return { good: walk(inflowGood), bad: walk(inflowBad), days, target, pay, bank, pending: false }
}
function CashChart({ ctx, sc, fc, received = 0, W = 780 }: { ctx?: GraphNode; sc?: GraphNode; fc?: GraphNode; received?: number; W?: number }) {
  const H = 220, base = 176, top = 14
  const { good, bad, days, target, pay, bank, pending } = useMemo(() => buildSeries(ctx, sc, fc, received), [ctx, sc, fc, received])
  const step = W / days, mid = Math.floor(days / 2)
  const maxV = Math.max(...good, 1) * 1.08, minV = Math.min(...bad, 0)
  const y = (v: number) => base - ((v - minV) / (maxV - minV)) * (base - top)
  const path = (pts: number[]) => pts.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const endG = good[days], endB = bad[days]
  return <div className="chart card">
    <div className="head"><b>Cash in the bank</b>{pending ? <span className="fine">today · projecting…</span> : <div className="legend"><span><i style={{ width: 14, height: 3, borderRadius: 2, background: 'var(--green)' }} />usual payers pay</span><span><i style={{ width: 14, height: 3, borderRadius: 2, background: 'var(--amber)' }} />slow payers slip</span></div>}</div>
    <svg viewBox={`0 0 ${W} ${H}`} fill="none">
      <path d={`${path(good)} L${W} ${y(0)} L0 ${y(0)} Z`} fill="#2CA01C" fillOpacity=".10" />
      <path d={`M0 ${y(0)} H${W}`} stroke="#D52B1E" strokeWidth="1.5" strokeDasharray="4 4" />
      <path d={path(bad)} stroke="#E08A00" strokeWidth="2" strokeDasharray="5 4" strokeLinejoin="round" />
      <path d={path(good)} stroke="#2CA01C" strokeWidth="2.5" strokeLinejoin="round" />
      <path d={`M${mid * step} ${top} V${base} M${W - 1} ${top} V${base}`} stroke="#8D9096" strokeWidth="1" strokeDasharray="3 4" />
      {!pending && <><circle cx={W - 2} cy={y(endG)} r="5" fill="#fff" stroke="#2CA01C" strokeWidth="2.5" /><circle cx={W - 2} cy={y(endB)} r="5" fill="#fff" stroke="#E08A00" strokeWidth="2" /></>}
      <text x="0" y={H - 6} fontSize="11" fill="#6B6C72">Today · ${k(bank)}{received ? " incl. payments" : ""}</text>
      <text x={mid * step} y={H - 6} fontSize="11" fontWeight="600" fill="#393A3D" textAnchor="middle">{fmtDate(shift(target, -7))} · payday</text>
      <text x={W - 4} y={H - 6} fontSize="11" fontWeight="600" fill="#393A3D" textAnchor="end">{fmtDate(target)} · payday</text>
      {!pending && <><text x={W - 12} y={Math.min(y(endG), y(endB) - 16) - 8} fontSize="12" fontWeight="700" fill="#2CA01C" textAnchor="end">{endG >= 0 ? '+' : '−'}${k(Math.abs(endG))}</text>
      <text x={W - 12} y={Math.max(y(endB), y(endG) + 16) + 16} fontSize="12" fontWeight="700" fill="#B35C00" textAnchor="end">{endB >= 0 ? '+' : '−'}${k(Math.abs(endB))}</text>
      <text x={mid * step + 8} y="26" fontSize="11" fill="#6B6C72">− ${k(pay / 2)} payroll</text></>}
    </svg>
  </div>
}
function Outcome({ fc, payments, levers }: { fc?: GraphNode; payments: GraphNode[]; levers: Lever[] }) {
  const d = fc?.data || {}
  const need = d.need || 1
  const nowC = LIVE ? (d.cash_at_target ?? 0) - need : (d.cushion ?? (d.gap > 0 ? -d.gap : d.cash_at_target ?? 0))
  const got = payments.reduce((a, p) => a + (p.data.amount || 0), 0)
  const before = LIVE ? (d.initial_cash_at_target ?? d.cash_at_target ?? 0) - (d.initial_need ?? need) : nowC - got
  const pct = (v: number) => `${Math.min(100, Math.max(2, 100 * Math.abs(v) / (need * 0.3)))}%`
  const fmt = (v: number) => `${v < 0 ? '−' : '+'}${money(Math.abs(v))}`
  const left = levers.filter(l => l.recovers)
  return <div className="card outcome">
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className="ic green" style={{ width: 22, height: 22 }}>{I.check}</span><b style={{ fontSize: 14 }}>Where you stand now</b><span className="fine" style={{ marginLeft: 'auto' }}>{payments.length} payment{payments.length > 1 ? 's' : ''} landed · {money(got)}</span></div>
    <div className="delta">
      <div className="d-col"><span className="fine">when you asked</span><b style={{ color: before < 0 ? 'var(--red)' : 'var(--amber-dk)' }}>{fmt(before)}</b><div className="bar"><i style={{ width: pct(before), background: before < 0 ? 'var(--red)' : 'var(--amber)' }} /></div></div>
      <div className="d-arrow">{I.arrow}</div>
      <div className="d-col"><span className="fine">now</span><b style={{ color: nowC < 0 ? 'var(--red)' : 'var(--green)' }}>{fmt(nowC)}</b><div className="bar"><i style={{ width: pct(nowC), background: nowC < 0 ? 'var(--red)' : 'var(--green)' }} /></div></div>
    </div>
    {left.length > 0 && <div className="fine">Still on the table: {left.map(l => `${l.label} (+${money(l.recovers)})`).join(' · ')}</div>}
  </div>
}
const shift = (d?: string, days = 0) => { if (!d) return undefined; const t = new Date(d + 'T00:00:00'); t.setDate(t.getDate() + days); return t.toISOString().slice(0, 10) }
function RiskPanel({ sc, fc }: { sc?: GraphNode; fc?: GraphNode }) {
  const risky = (sc?.rows || []).filter(r => r.p_paid_by_target < 0.7)
  const byCust = new Map<string, { customer: string; amount: number; wp: number; n: number; band: string }>()
  for (const r of risky) { const g = byCust.get(r.customer) || { customer: r.customer, amount: 0, wp: 0, n: 0, band: 'amber' }; g.amount += r.amount; g.wp += r.amount * r.p_paid_by_target; g.n++; if (r.band === 'red') g.band = 'red'; byCust.set(r.customer, g) }
  const groups = [...byCust.values()].sort((a, b) => b.amount - a.amount)
  const atRisk = groups.reduce((a, g) => a + g.amount, 0)
  const pess = fc?.data.pessimistic?.gap
  return <div className="card risk">
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className="ic amber" style={{ width: 22, height: 22 }}>{I.trend}</span><b style={{ fontSize: 14 }}>If the slow payers slip</b></div>
    <div className="kv" style={{ fontSize: 13 }}><span style={{ color: 'var(--muted)' }}>{risky.length} invoices from {groups.length} customers not reliable by payday</span><b>{money(atRisk)} at risk</b></div>
    <div className="risklist">
      {groups.slice(0, 4).map((g, i) => { const p = g.amount ? g.wp / g.amount : 0; return <div className="riskrow" key={g.customer}><span className="av" style={{ background: AV_COLORS[i % 5] }}>{initials(g.customer)}</span><span className="nm">{g.customer}<span className="fine"> · {g.n} inv</span></span><span className="am">{money(g.amount)}</span><span className={`pc ${p < 0.3 ? 'red' : 'amber'}`}>{Math.round(p * 100)}%</span></div> })}
      {groups.length > 4 && <div className="fine">+ {groups.length - 4} more customers</div>}
    </div>
    {pess != null && <div className="fine" style={{ color: 'var(--amber-dk)', fontWeight: 600 }}>Pessimistic scenario on payday: {pess > 0 ? `${money(pess)} short` : 'still covered'}</div>}
  </div>
}
function whoOf(n: GraphNode): string {
  const t = n.title || ''
  const m = t.match(/^Texting (.+)$/) || t.match(/^Negotiating with (.+?)['’]s agent$/) || t.match(/^(.+?) replied$/) || t.match(/^(.+?) paid /)
  return (m ? m[1] : t).split(' ')[0]
}
function Conversations({ actions }: { actions: GraphNode[]; decisions?: Decision[]; onDecide?: (d: Decision, opt: string) => void }) {
  const groups = new Map<string, GraphNode[]>()
  const idByFirst = new Map<string, string>()
  for (const a of actions) if (a.data.customer_id) idByFirst.set(whoOf(a), a.data.customer_id)
  for (const a of actions) { const w = a.data.customer_id || idByFirst.get(whoOf(a)) || whoOf(a); groups.set(w, [...(groups.get(w) || []), a]) }
  const threads = [...groups.entries()].map(([key, items], gi) => {
    const full = items.find(i => i.data.customer)?.data.customer || items.find(i => i.data.kind === 'reminder')?.title.replace(/^Texting /, '') || key
    const last = items[items.length - 1]
    const lastAt = Math.max(...items.map(i => i.doneAt || i.createdAt), ...items.flatMap(i => i.rounds.map(() => i.createdAt)))
    const preview = last.data.kind === 'payment' ? `Paid ${money(last.data.amount)}` : last.data.kind === 'negotiation' ? (last.data.agreement ? `Agreed: ${last.data.agreement.installments?.length} payments` : (last.rounds.at(-1)?.text || 'Negotiating…')) : last.data.kind === 'reply' ? last.data.text : String(last.data.draft?.body || last.title).slice(0, 60)
    const state = last.data.kind === 'payment' ? 'paid' : last.data.kind === 'negotiation' ? (last.data.agreement ? 'agreed' : 'negotiating') : last.data.kind === 'reply' ? 'replied' : last.status === 'done' ? 'sent' : 'sending'
    return { key, full, items, last, lastAt, preview, state, color: AV_COLORS[gi % 5] }
  })
  const newest = threads.reduce((a, t) => (!a || t.lastAt > a.lastAt ? t : a), threads[0])
  const [picked, setPicked] = useState<string | null>(null)
  const [pickedAt, setPickedAt] = useState(0)
  const sel = (picked && pickedAt > (newest?.lastAt || 0) ? threads.find(t => t.key === picked) : newest) || threads[0]
  if (!threads.length) return null
  const ago = (t: number) => { const s = Math.max(0, Math.round((Date.now() - t) / 1000)); return s < 60 ? 'now' : `${Math.round(s / 60)}m` }
  return <div className="msgs">
    <div className="mlist">
      <div className="mlist-h">Messages<span className="fine">{threads.length} customers</span></div>
      {threads.sort((a, b) => b.lastAt - a.lastAt).map(t => <div key={t.key} className={`mrow ${sel?.key === t.key ? 'sel' : ''}`} onClick={() => { setPicked(t.key); setPickedAt(Date.now()) }}>
        <span className="av" style={{ background: t.color }}>{initials(t.full)}</span>
        <div className="mtext"><div className="mtop"><b>{t.full}</b><span className="fine">{ago(t.lastAt)}</span></div><div className="mprev">{t.preview}</div></div>
        <span className={`state ${t.state}`}>{t.state}</span>
      </div>)}
    </div>
    <div className="mthread">
      <div className="mhead"><span className="av" style={{ background: sel.color }}>{initials(sel.full)}</span><div><b>{sel.full}</b><div className="fine">SMS · {BRAND} for Palletbay · {sel.items.some(i => i.data.channel === 'simulated') ? 'simulated, nothing sent' : 'pay link included'}</div></div></div>
      <div className="bubbles">
        {sel.items.map(a => {
          const d = a.data; const who = sel.full.split(' ')[0]
          if (d.kind === 'reminder') return <div key={a.node_id} className="bub out"><div>{String(d.draft?.body || a.title).replace('{pay_link}', 'pay.span.app/8f3a')}</div><span className="meta">{a.status === 'failed' ? 'failed' : d.channel === 'simulated' ? 'simulated' : a.status === 'done' ? 'Delivered' : 'Sending…'}</span></div>
          if (d.kind === 'reply') return <div key={a.node_id} className="bub in"><div>{d.text}</div><span className="meta">{String(d.classification || '').replace('_', ' ')}</span></div>
          if (d.kind === 'negotiation') return <div key={a.node_id} className="neg">
            <div className="fine" style={{ textAlign: 'center' }}>{BRAND}’s agent is talking to {who}’s agent{a.status === 'running' ? '…' : ''}</div>
            {a.rounds.map((r, i) => <div key={i} className={`bub ${r.from === 'owed' ? 'out agent' : 'in agent'}`}><div>{r.text}</div><span className="meta">{r.from === 'owed' ? `${BRAND} agent` : `${who}’s agent`}{r.p_honored ? ` · ${Math.round(r.p_honored * 100)}% likely honored` : ''}</span></div>)}
            {d.agreement && <div className="agree">{I.check} Agreed: {d.agreement.installments?.length} payments of {money(d.agreement.installments?.[0]?.amount)}</div>}
          </div>
          if (d.kind === 'payment') return <div key={a.node_id} className="receipt"><span className="ic green">{I.card}</span><div><b>{money(d.amount)} received</b><div className="fine">{String(d.rail).toUpperCase()} · card ending {d.receipt?.last4}</div></div></div>
          return <div key={a.node_id} className="fine">{a.title}</div>
        })}
      </div>
    </div>
  </div>
}

/* ---------- a thread = one run ---------- */
function HistoryStrip({ history }: { history: { amount: number; status: string; days_late: number | null; due_date: string }[] }) {
  const paid = history.filter(h => h.status === 'paid'); const avg = paid.length ? paid.reduce((a, h) => a + (h.days_late || 0), 0) / paid.length : 0
  const col = (h: { status: string; days_late: number | null }) => h.status === 'written_off' ? 'var(--red)' : (h.days_late ?? 0) <= 7 ? 'var(--green)' : (h.days_late ?? 0) <= 30 ? 'var(--amber)' : 'var(--red)'
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <div className="dots">{history.slice(-36).map((h, i) => <i key={i} style={{ background: col(h), height: 11 + Math.min(14, Math.max(0, (h.days_late ?? 0) / 3)), borderRadius: 3, width: 8 }} title={`${h.due_date} · ${h.days_late ?? '—'} days late · ${money(h.amount)}`} />)}</div>
    <div className="kv"><span style={{ color: 'var(--muted)' }}>{paid.length} invoices paid, usually {Math.round(avg)} days late</span><b>{history.filter(h => h.status === 'written_off').length ? `${history.filter(h => h.status === 'written_off').length} written off` : 'never written off'}</b></div>
    <div className="legend"><span><i style={{ background: 'var(--green)' }} />on time-ish</span><span><i style={{ background: 'var(--amber)' }} />late</span><span><i style={{ background: 'var(--red)' }} />very late / lost</span></div>
  </div>
}
const smoney = (v: number) => v < 0 ? `−${money(-v)}` : money(v)
/** Weekly low balances from the planner's cash tools; red below zero, faint bars = without the new cost. */
function WeeklyCash({ weeks, baseline }: { weeks: { week_ending: string; low: number }[]; baseline?: { week_ending: string; low: number }[] }) {
  const all = [...weeks, ...(baseline || [])].map(w => Math.abs(w.low)); const max = Math.max(1, ...all)
  const bar = (v: number, faint?: boolean) => <i style={{ display: 'block', width: faint ? 6 : 10, height: Math.max(2, (Math.abs(v) / max) * 36), background: v < 0 ? 'var(--red)' : 'var(--green)', opacity: faint ? 0.35 : 1, borderRadius: 2, alignSelf: v < 0 ? 'flex-start' : 'flex-end' }} />
  return <div style={{ display: 'flex', gap: 10, alignItems: 'stretch', margin: '2px 0 8px' }}>{weeks.map((w, i) => <div key={w.week_ending} title={`Week to ${fmtDate(w.week_ending)} · low ${smoney(w.low)}${baseline?.[i] ? ` (without: ${smoney(baseline[i].low)})` : ''}`} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
    <div style={{ height: 36, display: 'flex', alignItems: 'flex-end', gap: 2 }}>{baseline?.[i] && baseline[i].low >= 0 && bar(baseline[i].low, true)}{w.low >= 0 && bar(w.low)}</div>
    <div style={{ height: 1, width: '100%', minWidth: 14, background: 'var(--line, #ddd)' }} />
    <div style={{ height: 36, display: 'flex', alignItems: 'flex-start', gap: 2 }}>{baseline?.[i] && baseline[i].low < 0 && bar(baseline[i].low, true)}{w.low < 0 && bar(w.low)}</div>
    <span className="fine" style={{ fontSize: 10 }}>{fmtDate(w.week_ending)}</span></div>)}</div>
}
/** Planner answer tools (cash outlook, affordability, bills, customers, receivables, orders): one card per result shape. */
function AnswerToolNode({ n }: { n: GraphNode }) {
  const d = n.data || {}
  const head = (icon: React.ReactNode, cls: string, title: string, extra?: React.ReactNode) => <h3><span className={`ic ${cls}`}>{icon}</span>{title}{extra}{n.status === 'running' && <span className="fine" style={{ marginLeft: 'auto' }}>working…</span>}</h3>
  if (Array.isArray(d.weekly) && d.low_point) return <div className={`node ${n.status}`}>{head(I.book, 'blue', d.spend ? `Tested ${money(d.spend.amount)}${d.spend.frequency === 'once' ? '' : ' ' + d.spend.frequency} against cash` : `Daily cash to ${fmtDate(d.target_date)}`)}<WeeklyCash weeks={d.weekly} baseline={d.weekly_baseline} />
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {d.spend && <div className="kv"><span style={{ color: 'var(--muted)' }}>Low point without it</span><b>{smoney(d.baseline.low_point.balance)} · {fmtDate(d.baseline.low_point.date)}</b></div>}
      <div className="kv"><span style={{ color: 'var(--muted)' }}>{d.spend ? 'Low point with it' : 'Low point'}</span><b style={{ color: d.low_point.balance < 0 ? 'var(--red)' : undefined }}>{smoney(d.low_point.balance)} · {fmtDate(d.low_point.date)}</b></div>
      {!d.spend && d.first_negative_date && <div className="kv"><span style={{ color: 'var(--muted)' }}>First day below zero</span><b>{fmtDate(d.first_negative_date)}</b></div>}
      {!d.spend && d.pessimistic_low_point && <div className="kv"><span style={{ color: 'var(--muted)' }}>If slow payers slip</span><b>{smoney(d.pessimistic_low_point.balance)}</b></div>}
    </div></div>
  if (Array.isArray(d.bills) && d.through_date) return <div className={`node ${n.status}`}>{head(I.book, 'blue', `${d.count} unpaid bill${d.count === 1 ? '' : 's'} through ${fmtDate(d.through_date)}`, <b style={{ marginLeft: 8 }}>{money(d.total)}</b>)}<div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflow: 'auto' }}>
    {d.bills.map((b: any) => <div className="kv" key={b.bill_id}><span style={{ color: 'var(--muted)' }}>{b.vendor_name} · {b.status === 'overdue' ? <span style={{ color: 'var(--red)' }}>overdue {fmtDate(b.due_date)}</span> : `due ${fmtDate(b.due_date)}`}</span><b>{money(b.amount)}</b></div>)}
    {d.bills.length === 0 && <div className="fine">No unpaid bills match.</div>}</div></div>
  if (d.order && d.payment_outlook) { const po = d.payment_outlook; return <div className={`node ${n.status}`}>{head(I.people, 'blue', `${money(d.order.amount)} order · ${d.order.customer} · net ${d.order.terms_days}`)}<div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <div className="kv"><span style={{ color: 'var(--muted)' }}>Likely paid</span><b>{fmtDate(po.expected_pay_date)} (~{Math.round(po.expected_days_late)} days late)</b></div>
    <div className="kv"><span style={{ color: 'var(--muted)' }}>Chance it is never paid</span><b>{Math.round(po.p_never * 100)}%</b></div>
    <div className="kv"><span style={{ color: 'var(--muted)' }}>They would owe you</span><b>{money(d.exposure_after_order)}</b></div>
    {d.low_point && <div className="kv"><span style={{ color: 'var(--muted)' }}>Cash low point after up-front cost</span><b style={{ color: d.low_point.balance < 0 ? 'var(--red)' : undefined }}>{smoney(d.low_point.balance)} · {fmtDate(d.low_point.date)}</b></div>}
  </div></div> }
  if (d.aging && d.owed_total != null) { const total = Math.max(1, d.owed_total); const cols: Record<string, string> = { not_yet_due: 'var(--green)', '1_30_days': 'var(--amber)', '31_60_days': 'var(--amber)', '61_90_days': 'var(--red)', over_90_days: 'var(--red)' }
    return <div className={`node ${n.status}`}>{head(I.book, 'blue', `${money(d.owed_total)} owed to you`)}<div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', margin: '2px 0 8px' }}>{Object.entries(d.aging as Record<string, number>).filter(([, v]) => v > 0).map(([key, v]) => <i key={key} title={`${key.replace(/_/g, ' ')} · ${money(v)}`} style={{ width: `${(v / total) * 100}%`, background: cols[key], opacity: key === '1_30_days' ? 0.7 : 1 }} />)}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><div className="kv"><span style={{ color: 'var(--muted)' }}>Overdue</span><b>{money(d.overdue_total)} · {d.overdue_invoices} invoices</b></div><div className="kv"><span style={{ color: 'var(--muted)' }}>Not yet due</span><b>{money(d.not_yet_due_total)}</b></div><div className="kv"><span style={{ color: 'var(--muted)' }}>Likely in next 30 days</span><b>{money(d.expected_in_30_days)}</b></div></div></div> }
  if (Array.isArray(d.customers) && d.customers.length && d.customers[0].open_balance !== undefined) return <div className={`node ${n.status}`}>{head(I.people, 'blue', d.ranked_by ? `Ranked customers · ${String(d.ranked_by).replace(/_/g, ' ')}` : d.customers.length === 1 ? 'Found the customer' : `${d.matches ?? d.customers.length} customers match “${d.query}”`)}<div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    {d.customers.slice(0, 6).map((c: any, i: number) => <div className="kv" key={c.id} style={{ alignItems: 'center' }}><span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}><span className="av" style={{ background: AV_COLORS[i % 5], width: 18, height: 18, borderRadius: 9, color: '#fff', fontSize: 9, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>{initials(c.display_name)}</span><span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.display_name}</span></span><b style={{ whiteSpace: 'nowrap' }}>{c.avg_days_late != null ? `${Math.round(c.avg_days_late)}d late avg · ` : ''}{money(c.overdue_balance)} overdue</b></div>)}
  </div></div>
  if (d.customers && !d.customers.length) return <div className={`node ${n.status}`}>{head(I.people, 'grey', `No customer matches “${d.query ?? ''}”`)}</div>
  if (d.status === 'not_supported') return <div className={`node ${n.status}`}>{head(I.book, 'grey', `Deferral not scheduled · ${d.vendor_name ?? d.bill_id}`)}<div className="fine">{d.reason}</div></div>
  return <NoteNode n={n} />
}
function CustomerNode({ n }: { n: GraphNode }) {
  const d = n.data, s = d.summary || {}, who = d.customer?.display_name || n.rows[0]?.customer || 'Customer'
  const col = { green: 'var(--green)', amber: 'var(--amber)', red: 'var(--red)' }
  const hist: any[] = (d.history || []).slice(-24)
  const working = n.status === 'running' && !n.rows.length && !hist.length
  return <div className={`node ${n.status}`}>
    <h3><span className="ic green">{I.person}</span>{who}{n.status === 'running' && <span className="fine" style={{ marginLeft: 'auto' }}>reading history…</span>}</h3>
    {working ? <div className="thinking"><i/><i/><i/> scoring</div> : <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="fine">Open invoices · {n.rows.length}{s.open_total != null ? ` · ${money(s.open_total)}` : ''}</div>
        <div className="dots">{n.rows.map(r => <i key={r.invoice_id} style={{ background: col[r.band] || col.amber }} title={`${r.invoice_id} · $${Math.round(r.amount)} · ${r.days_past_due}d · ${Math.round(r.p_paid_by_target * 100)}% by target`} />)}</div>
        <div className="legend"><span><i style={{ background: 'var(--green)' }} />will pay</span><span><i style={{ background: 'var(--amber)' }} />maybe</span><span><i style={{ background: 'var(--red)' }} />unlikely</span></div>
        {n.rows.slice(0, 4).map(r => <div className="kv" key={r.invoice_id}><span>{r.invoice_id}<span className="fine"> · {r.days_past_due > 0 ? `${r.days_past_due}d late` : 'not due yet'}</span></span><b>{money(r.amount)} · {Math.round(r.p_paid_by_target * 100)}%</b></div>)}
      </div>
      {hist.length > 0 && <HistoryStrip history={d.history} />}
    </>}
  </div>
}
function BillsNode({ n }: { n: GraphNode }) {
  const bills: any[] = n.data.bills || []
  return <div className={`node ${n.status}`}><h3><span className="ic blue">{I.cal}</span>Bills due by {fmtDate(n.data.target_date)}</h3>
    {!bills.length ? <div className="fine">{n.status === 'running' ? 'reading…' : 'Nothing due in the window.'}</div>
      : <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>{bills.slice(0, 6).map(b => <div className="kv" key={b.bill_id}><span>{b.vendor_name}<span className="fine"> · {fmtDate(b.due_date)}</span></span><b>{money(Number(b.open_amount))}</b></div>)}{bills.length > 6 && <div className="fine">+ {bills.length - 6} more</div>}</div>}
  </div>
}
function CustomersNode({ n }: { n: GraphNode }) {
  const cs: any[] = n.data.customers || []
  return <div className={`node ${n.status}`}><h3><span className="ic blue">{I.people}</span>{cs.length ? `${cs.length} customers` : 'Customers'}</h3>
    {!cs.length ? <div className="fine">{n.status === 'running' ? 'reading…' : 'None on file.'}</div>
      : <div className="chips">{cs.slice(0, 18).map((c, i) => <span className="chip" key={c.id}><span className="av" style={{ background: AV_COLORS[i % 5] }}>{initials(c.display_name)}</span>{c.display_name}</span>)}{cs.length > 18 && <span className="chip plain">+ {cs.length - 18} more</span>}</div>}
  </div>
}
function ApprovalNode({ n, decision, onDecide }: { n: GraphNode; decision?: Decision; onDecide: (d: Decision, opt: string) => void }) {
  const d = n.data
  const what = d.tool === 'defer_bill' ? `Defer bill ${d.bill_id}` : d.tool === 'send_message' ? `Send a reminder for ${d.invoice_id}` : n.title
  return <div className={`node ${n.status}`}><h3><span className="ic amber">{I.star}</span>{what}</h3>
    {d.error ? <div className="fine" style={{ color: 'var(--red)' }}>{d.error}</div>
      : decision ? (decision.resolved ? <button className="btn done" disabled>{I.check} {decision.resolved === 'no' ? 'Not now' : 'Approved'}</button>
        : <div style={{ display: 'flex', gap: 8 }}>{decision.options.map(o => <button key={o.id} className={`btn ${o.id === 'yes' ? 'primary' : ''}`} onClick={() => onDecide(decision, o.id)}>{o.label}</button>)}</div>)
      : <div className="fine">{['approval_required', 'waiting_for_owner'].includes(d.status) ? 'Waiting for your approval' : n.status === 'running' ? 'working…' : 'Done'}</div>}
  </div>
}
function DraftNode({ n }: { n: GraphNode }) {
  const d = n.data
  return <div className={`node ${n.status}`}><h3><span className="ic blue">{I.chat}</span>Draft · {d.invoice_id || ''}{d.tone && <span className="chip plain" style={{ marginLeft: 8 }}>{d.tone}</span>}</h3>
    {d.body ? <div className="bub out" style={{ maxWidth: 420 }}><div>{String(d.body)}</div><span className="meta">not sent</span></div> : <div className="fine">drafting…</div>}
  </div>
}
function NoteNode({ n }: { n: GraphNode }) {
  const d = n.data || {}
  const facts = Object.entries(d).filter(([k, v]) => typeof v === 'number' && !/id$/.test(k)).slice(0, 4)
  return <div className={`node ${n.status}`}><h3><span className="ic blue">{I.book}</span>{n.title}{n.status === 'running' && <span className="fine" style={{ marginLeft: 'auto' }}>working…</span>}</h3>
    {d.error && <div className="fine" style={{ color: 'var(--red)' }}>{d.error}</div>}
    {d.text && <div style={{ fontSize: 14, lineHeight: '20px' }}>{plain(d.text)}</div>}
    {!d.text && facts.length > 0 && <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>{facts.map(([k, v]) => <div className="kv" key={k}><span style={{ color: 'var(--muted)' }}>{k.replace(/_/g, ' ')}</span><b>{Math.abs(v as number) >= 100 ? money(v as number) : String(v)}</b></div>)}</div>}
  </div>
}
/** Verdict strip: a yes/no word and the headline number lifted from the spoken answer. */
function AnswerStrip({ n }: { n: GraphNode }) {
  const d = n.data || {}
  const v: string | undefined = d.verdict ?? (d.answer === 'yes' || d.answer === 'no' ? d.answer : undefined)
  const num: number | undefined = d.number ?? (d.gap > 0 ? d.gap : undefined)
  if (!v && num == null) return <div className={`node ${n.status}`}><h3><span className="ic green">{I.check}</span>Answer</h3><div style={{ fontSize: 15, lineHeight: '22px', fontWeight: 600 }}>{plain(d.spoken || n.title)}</div></div>
  const cls = v === 'no' ? 'bad' : v === 'yes' ? 'ok' : ''
  const word = v === 'yes' ? 'Yes.' : v === 'no' ? 'No.' : v === 'barely' ? 'Barely.' : money(num)
  return <div className={`node verdict ${cls}`}>
    <div className="big">{word}</div>
    {v && num != null && <div className="sub">{money(num)}</div>}
    <div className="fine" style={{ flex: 1 }}>{plain(d.spoken || n.title)}</div>
  </div>
}
function toolOf(n: GraphNode): string {
  if (n.data?.tool) return n.data.tool
  const t = (n.title || '').toLowerCase().replace(/ /g, '_')  // runs recorded before data.tool existed
  return ['forecast_cash', 'rank_chase', 'score_customer', 'predict_payment', 'query_books', 'draft_reminder', 'send_message', 'defer_bill', 'show_node', 'resolve_decision'].find(x => t.startsWith(x)) || ''
}
const ANSWER_TOOLS = ['cash_outlook', 'check_affordability', 'list_bills', 'evaluate_order', 'receivables_summary', 'find_customer', 'rank_customers']
function PlannerStep({ n, run, onDecide }: { n: GraphNode; run: RunState; onDecide: (d: Decision, opt: string, selected?: string[]) => void }) {
  const tool = toolOf(n), d = n.data || {}
  if (n.status === 'failed') return <NoteNode n={n} />
  const decision = Object.values(run.decisions).find(x => x.node_id === n.node_id || (d.decision_id && x.decision_id === d.decision_id))
  if (n.node_id === 'context' && d.question) return <QuestionNode question={d.question} />
  if (n.type === 'answer') return <AnswerStrip n={n} />
  if (tool === 'forecast_cash') return <CashNode n={n} ctx={n} />
  if (tool === 'score_customer' || tool === 'predict_payment') return <CustomerNode n={n} />
  if (ANSWER_TOOLS.includes(tool) || d.status === 'not_supported') return <AnswerToolNode n={n} />
  if (tool === 'query_books') {
    if (d.rows || d.invoices) return <ScoredNode n={n} />
    if (d.bills) return <BillsNode n={n} />
    if (d.customers) return <CustomersNode n={n} />
    if (d.bank_balance != null || n.status === 'running') return <BooksNode n={n} />
  }
  if (tool === 'rank_chase') {
    const levers: Lever[] = d.levers || []
    if (!levers.length) return <div className={`node ${n.status}`}><h3><span className="ic green">{I.star}</span>{n.title}</h3><div className="fine">{n.status === 'running' ? 'working out what would close the gap…' : d.error || 'No supported levers found.'}</div></div>
    return <div className="levers" style={{ width: '100%' }}>{levers.map(l => <div key={l.id} style={{ flex: 1, display: 'flex', minWidth: 0 }}><LeverCard l={l} rec={(d.recommended || ['chase'])[0] === l.id} decision={decision} chosen={decision?.resolved} onChoose={(opt, selected) => decision && onDecide(decision, opt, selected)} /></div>)}</div>
  }
  if (tool === 'send_message' || tool === 'defer_bill' || d.status === 'approval_required') return <ApprovalNode n={n} decision={decision} onDecide={onDecide} />
  if (tool === 'draft_reminder') return <DraftNode n={n} />
  return <NoteNode n={n} />
}
function Detail({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map(b => b.trim()).filter(Boolean)
  return <div className="detail">{blocks.map((b, i) => {
    const lines = b.split('\n').map(l => l.replace(/\*\*|`/g, ''))
    if (/^#+\s/.test(lines[0])) return <div key={i}><b>{lines[0].replace(/^#+\s*/, '')}</b>{lines.slice(1).map((l, j) => <div key={j}>{l.replace(/^\s*[-*]\s+/, '• ')}</div>)}</div>
    return <div key={i}>{lines.map((l, j) => <div key={j}>{l.replace(/^\s*[-*]\s+/, '• ')}</div>)}</div>
  })}</div>
}
function Reasoning({ detail }: { detail: string }) {
  const [open, setOpen] = useState(false)
  return <div className={`node reasoning ${open ? 'open' : ''}`} onClick={() => setOpen(o => !o)}>
    <h3><span className="ic grey">{I.book}</span>Full reasoning<span className="fine" style={{ marginLeft: 'auto' }}>{open ? 'hide' : 'show'} · also in the report</span></h3>
    {open && <Detail text={detail} />}
  </div>
}
/** Gemini/voice runs use context, tool-*, answer and planner-error ids; payroll runs use n1…n5, branches f1… or late-scoring. */
const isPlannerRun = (r: RunState) => r.order.some(id => id.startsWith('tool-') || id === 'context' || id === 'answer' || id === 'planner-error')
function QuestionNode({ question }: { question: string }) {
  return <div className="node question-node"><h3><span className="ic grey">{I.chat}</span>Your question</h3><div>{question}</div></div>
}
function BranchHeading({ run, parent }: { run: RunState; parent?: RunState }) {
  if (!run.parent_run_id) return null
  return <div className="branch"><span className="ic grey" style={{ width: 20, height: 20 }}>{I.chat}</span><span>Follow-up · branches from <a href={`#thread-${run.parent_run_id}`}>{parent?.question || run.parent_run_id}</a></span></div>
}
function PlannerThread({ run, parent, onDecide, reportFailedFor, retryReportFor }: { run: RunState; parent?: RunState; onDecide: (d: Decision, opt: string, selected?: string[]) => void; reportFailedFor?: (r: RunState) => boolean; retryReportFor?: (r: RunState) => void }) {
  const nodes = run.order.map(id => run.nodes[id])
  const ans = nodes.find(n => n.type === 'answer')
  // the planner's "context" node only echoes the question, which the question card already shows
  const tools = nodes.filter(n => n.type !== 'answer' && (n.type !== 'action' || toolOf(n)) && !(n.node_id === 'context' && !n.data?.company && !n.data?.customers))
  const fcNode = nodes.find(n => n.data?.cash_at_target != null)
  const actions = nodes.filter(n => n.type === 'action' && !toolOf(n))
  const sc = nodes.find(n => n.rows.length > 0)
  const ctxLike: GraphNode | undefined = fcNode ? { ...fcNode, data: { ...fcNode.data, payroll_due_by_target: fcNode.data.need } } : undefined
  return <section className="thread">
    <BranchHeading run={run} parent={parent} />
    <div className="workspace">
      <aside className="live">
        {ctxLike && (LIVE ? <div className="chart-wrap card"><DailyCashChart company={run.company_id || COMPANY} target={ctxLike.data.target_date} revision={`${fcNode?.data.forecast_id}:${fcNode?.data.cash_at_target}`} neverPays={fcNode?.data.excluded_customer_id} willPay={fcNode?.data.assumed_customer_id} /></div> : <CashChart ctx={ctxLike} fc={fcNode} W={420} />)}
        {LIVE && fcNode && <ForecastHistory company={run.company_id || COMPANY} runId={run.run_id} revision={String(fcNode.data.forecast_id || fcNode.data.cash_at_target)} />}
        {sc && sc.rows.length > 1 && <RiskPanel sc={sc} fc={fcNode} />}
        <div className={`card report ${run.report_id ? 'ready' : ''}`}><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className={`ic ${run.report_id ? 'green' : 'grey'}`} style={{ width: 22, height: 22 }}>{I.book}</span><b style={{ fontSize: 14 }}>One-page report</b></div>{run.report_id ? <a className="btn" href={`/report/${run.report_id}?company=${encodeURIComponent(COMPANY)}`}>Open report</a> : ans?.data.awaiting_input ? <div className="fine">Waiting for your answer before continuing.</div> : reportFailedFor?.(run) ? <button className="btn" onClick={() => retryReportFor?.(run)}>Generate report</button> : run.status === 'closed' ? <div className="thinking"><i/><i/><i/> writing</div> : <div className="fine">Builds itself when this run finishes.</div>}</div>
      </aside>
      <div className="steps">
        <div className="vstep"><QuestionNode question={run.question} /></div>
        {tools.map(n => <div key={n.node_id}><div className="vconn" /><div className="vstep"><PlannerStep n={n} run={run} onDecide={onDecide} /></div></div>)}
        {ans && !ans.data.awaiting_input && ans.status !== 'failed' ? <><div className="vconn" /><div className="vstep"><AnswerStrip n={ans} /></div></> : ans && <><div className="vconn" /><div className="vstep"><div className={`node ${ans.status}`}><h3><span className={`ic ${ans.status === 'failed' ? 'grey' : 'green'}`}>{I.chat}</span>{ans.data.awaiting_input ? `${BRAND} needs one answer` : ans.status === 'failed' ? `${BRAND} couldn’t finish` : `${BRAND}’s answer`}</h3><div style={{ flex: 1, fontSize: 14, lineHeight: '20px' }}>{plain(ans.data.spoken || ans.title)}</div></div></div></>}
        {actions.length > 0 && <><div className="vconn" /><Conversations actions={actions} decisions={Object.values(run.decisions)} onDecide={onDecide} /></>}
        {ans?.data.detail && <><div className="vconn" /><div className="vstep"><Reasoning detail={ans.data.detail} /></div></>}
        {!ans && <div className="thinking" style={{ marginTop: 14 }}><i/><i/><i/> {BRAND} is thinking</div>}
      </div>
    </div>
  </section>
}
function Thread({ run, onDecide, isFollowUp, parent, reportFailedFor, retryReportFor }: { run: RunState; onDecide: (d: Decision, opt: string, selected?: string[]) => void; isFollowUp?: boolean; parent?: RunState; reportFailedFor?: (r: RunState) => boolean; retryReportFor?: (r: RunState) => void }) {
  const byType = (t: string) => run.order.map(id => run.nodes[id]).find(n => n.type === t)
  const ctx = byType('context'), sc = byType('scoring'), fc = byType('forecast'), ans = byType('answer'), lv = byType('levers')
  const actions = run.order.map(id => run.nodes[id]).filter(n => n.type === 'action')
  const payments = actions.filter(a => a.data.kind === 'payment'); const received = payments.reduce((a, p) => a + (p.data.amount || 0), 0)
  const levers: Lever[] = lv?.data.levers || []
  const decision = Object.values(run.decisions).find(d => d.node_id === lv?.node_id)
  const chosen = decision?.resolved
  const verdictRef = useRef<HTMLDivElement | null>(null), contRef = useRef<HTMLDivElement | null>(null)
  const leverRefs = useMemo(() => levers.map(() => ({ current: null as HTMLDivElement | null })), [levers.length])
  if (isFollowUp) {
    const pfc = parent ? parent.order.map(id => parent.nodes[id]).find(n => n.type === 'forecast') : undefined
    const scenario = run.order.map(id => run.nodes[id]).find(n => n.type === 'context' && /what-if|scenario|without/i.test(n.title + ' ' + JSON.stringify(n.data || {})))
    const lateList = !fc && sc && /overdue|late/i.test(sc.title)
    const gapNow = fc ? (fc.data.gap > 0 ? -fc.data.gap : (fc.data.need != null && (fc.data.cash_at_target ?? 0) >= fc.data.need ? fc.data.cash_at_target - fc.data.need : (fc.data.cash_at_target ?? 0))) : undefined
    const gapWas = pfc ? (pfc.data.gap > 0 ? -pfc.data.gap : (pfc.data.need != null && (pfc.data.cash_at_target ?? 0) >= pfc.data.need ? pfc.data.cash_at_target - pfc.data.need : (pfc.data.cash_at_target ?? 0))) : undefined
    return <section className="thread followup">
      <BranchHeading run={run} parent={parent} />
      <div className="steps" ref={contRef}>
        <div className="vstep"><QuestionNode question={run.question} /></div>
        {scenario && <div className="fine" style={{ marginBottom: 10 }}>Scenario: {scenario.title.replace(/^What-if scenario\s*/i, '')}{scenario.data?.excluded_customer ? ` · without ${scenario.data.excluded_customer}` : ''}</div>}
        {fc && fc.status === 'done' && gapNow != null && <div className="vstep"><div className={`node verdict ${gapNow < 0 ? 'bad' : gapNow < (fc.data.need || 1) * 0.1 ? '' : 'ok'}`}>
          <Gauge cushion={gapNow} need={fc.data.need || 20000} />
          <div className="big">{gapNow < 0 ? 'No.' : gapNow < (fc.data.need || 1) * 0.1 ? 'Barely.' : 'Yes.'}</div>
          <div className="sub">{gapNow < 0 ? `${money(-gapNow)} short` : `${money(gapNow)} to spare`}</div>
          <div className="fine">{gapWas != null ? `was ${gapWas < 0 ? money(-gapWas) + ' short' : money(gapWas) + ' to spare'} before this scenario` : ''}{fc.data.pessimistic?.gap > 0 ? ` · ${money(fc.data.pessimistic.gap)} short if slow payers slip` : ''}</div>
        </div></div>}
        {lateList && <div className="vstep"><div className="node"><h3><span className="ic amber">{I.people}</span>{sc!.title}</h3>
          <div className="latelist">{sc!.rows.slice().sort((a, b) => b.days_past_due - a.days_past_due).slice(0, 12).map((r, i) => <div className="laterow" key={r.invoice_id}><span className="av" style={{ background: AV_COLORS[i % 5] }}>{initials(r.customer)}</span><span className="nm">{r.customer}<span className="fine"> · {r.invoice_id}</span></span><span className="am">{r.days_past_due}d late</span><b className="am">{money(r.amount)}</b><span className={`pc ${r.band}`} style={{ color: r.band === 'green' ? 'var(--green)' : r.band === 'amber' ? 'var(--amber-dk)' : 'var(--red)' }}>{Math.round(r.p_paid_by_target * 100)}%</span></div>)}{sc!.rows.length > 12 && <div className="fine">+ {sc!.rows.length - 12} more</div>}</div></div></div>}
        {levers.length > 0 && <div className="levers" style={{ marginTop: 12 }}>{levers.map((l, i) => <div key={l.id} ref={el => { leverRefs[i].current = el }} style={{ flex: 1, display: 'flex', minWidth: 0 }}><LeverCard l={l} rec={(lv?.data.recommended || ['chase'])[0] === l.id} decision={decision} chosen={chosen} onChoose={(opt, selected) => decision && onDecide(decision, opt, selected)} /></div>)}</div>}
        {actions.length > 0 && <><div className="vconn" style={{ marginTop: 4 }} /><Conversations actions={actions} decisions={Object.values(run.decisions)} onDecide={onDecide} /></>}
        {!fc && !lateList && !levers.length && !actions.length && (ans ? <div className="vstep"><div className="node"><h3><span className="ic grey">{I.chat}</span>{plain(ans.data.spoken || ans.title)}</h3></div></div> : <div className="thinking"><i/><i/><i/> working</div>)}
      </div>
    </section>
  }
  return <section className="thread">
    {isFollowUp && <BranchHeading run={run} parent={parent} />}
    <div className="workspace">
      <aside className="live">
        {ctx && (LIVE
          ? fc?.status === 'done'
            ? <div className="chart-wrap card">{fc.data.excluded_customer_id && <div className="scenario-label"><b>What-if scenario</b><span>{fc.title.replace(/^Forecasting /, '')}</span><span>Actual payments already received stay in cash.</span></div>}<DailyCashChart company={run.company_id || COMPANY} target={fc.data.target_date || ctx?.data.target_date || ctx?.data.payroll_date} revision={`${fc.data.cash_at_target}:${fc.data.owed_total}`} neverPays={fc.data.excluded_customer_id} /></div>
            : <div className="card chart">Calculating this thread’s cash projection…</div>
          : <CashChart ctx={ctx} sc={sc} fc={fc} received={received} W={420} />)}
        {sc && sc.rows.length > 0 && <RiskPanel sc={sc} fc={fc} />}
        {LIVE && fc && <ForecastHistory company={run.company_id || COMPANY} runId={run.run_id} revision={String(fc.data.forecast_id || fc.data.cash_at_target)} />}
        <div className={`card report ${run.report_id ? 'ready' : ''}`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className={`ic ${run.report_id ? 'green' : 'grey'}`} style={{ width: 22, height: 22 }}>{I.book}</span><b style={{ fontSize: 14 }}>One-page report</b></div>
          <div className="fine">{run.report_id ? 'Ready. Share it with your bookkeeper or print it.' : run.status === 'closed' ? 'Putting the page together.' : 'Builds itself when this run finishes.'}</div>
          {run.report_id ? <a className="btn" href={`/report/${run.report_id}?company=${encodeURIComponent(COMPANY)}`}>Open report</a> : reportFailedFor?.(run) ? <button className="btn" onClick={() => retryReportFor?.(run)}>Generate report</button> : run.status === 'closed' ? <div className="thinking"><i/><i/><i/> writing</div> : <div className="fine" style={{ color: 'var(--muted2)' }}>waiting for the run to finish</div>}
        </div>
      </aside>
      <div className="steps" ref={contRef}>
        <div className="vstep"><QuestionNode question={run.question} /></div>
        {ctx && <><div className="vconn" /><div className="vstep"><BooksNode n={ctx} /></div></>}
        {sc && <><div className="vconn" /><div className="vstep"><ScoredNode n={sc} /></div></>}
        {fc && <><div className="vconn" /><div className="vstep"><CashNode n={fc} ctx={ctx} /></div></>}
        {ans && <><div className="vconn" /><div className="vstep" ref={verdictRef}><VerdictNode n={ans} fc={fc} /></div></>}
        {levers.length > 0 && <>
          <Fork fromRef={verdictRef} toRefs={leverRefs} containerRef={contRef} />
          <div className="levers">{levers.map((l, i) => <div key={l.id} ref={el => { leverRefs[i].current = el }} style={{ flex: 1, display: 'flex', minWidth: 0 }}><LeverCard l={l} rec={(lv?.data.recommended || ['chase'])[0] === l.id} decision={decision} chosen={chosen} onChoose={(opt, selected) => decision && onDecide(decision, opt, selected)} /></div>)}</div>
        </>}
        {lv && levers.length === 0 && <div className="thinking" style={{ marginTop: 16 }}><i/><i/><i/> working out what would close the gap</div>}
        {actions.length > 0 && <><div className="vconn" style={{ marginTop: 4 }} /><Conversations actions={actions} decisions={Object.values(run.decisions)} onDecide={onDecide} /></>}
        {payments.length > 0 && <><div className="vconn" /><Outcome fc={fc} payments={payments} levers={levers} /></>}
      </div>
    </div>
  </section>
}

/* ---------- bottom-right dock: call transcript + chat ---------- */
function Dock({ run, elapsed, input, setInput, onAsk, live, onReplay, browserVoice }: { run: RunState; elapsed: number; input: string; setInput: (s: string) => void; onAsk: (q: string) => void; live: boolean; onReplay: (speed: number) => void; browserVoice: boolean }) {
  const [open, setOpen] = useState(browserVoice)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle')
  const [voiceMessage, setVoiceMessage] = useState('')
  const stopListening = useRef<() => void>(() => {})
  const onCall = run.status === 'open'
  const lastOwed = [...run.turns].reverse().find(t => t.kind === 'owed')
  const [preview, setPreview] = useState<string | null>(null)
  useEffect(() => {
    if (open || !lastOwed || Date.now() - lastOwed.at > 8000) { setPreview(null); return }
    const short = plain(lastOwed.text); setPreview(short.length > 150 ? short.slice(0, 147).replace(/\s+\S*$/, '') + '…' : short)
    const t = setTimeout(() => setPreview(null), 7000); return () => clearTimeout(t)
  }, [lastOwed?.text, lastOwed?.at, open])
  const mm = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`
  const scroller = useRef<HTMLDivElement | null>(null)
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' }) }, [run.turns.length, open])
  useEffect(() => () => stopListening.current(), [])
  const send = () => { const q = input.trim(); if (q) onAsk(q) }
  const startVoiceFollowUp = () => {
    setVoiceMessage('')
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    stopListening.current()
    stopListening.current = listenOnce(
      text => { stopListening.current(); setVoiceStatus('idle'); onAsk(text) },
      (status, message) => { setVoiceStatus(status); setVoiceMessage(message || '') },
    )
  }
  return <div className={`dock ${open ? 'open' : ''}`}>
    {open && <div className="dpanel">
      <div className="dhead" onClick={() => setOpen(false)}>
        <span className="ic green">{I.phone}</span>
        <div style={{ flex: 1 }}><b>{browserVoice ? 'Browser voice demo' : onCall ? `On a call · ${mm}` : 'Call ended'}</b><div className="fine">{browserVoice ? 'Tap the mic to speak one follow-up. Browser speech, not telephony.' : onCall ? 'Listening · tool rows show what ' + BRAND + ' did between sentences' : 'Transcript saved'}</div></div>
        <div className={`wave ${onCall ? '' : 'idle'}`}>{Array.from({ length: 7 }).map((_, i) => <i key={i} style={{ height: 4 + ((i * 7) % 14) }} />)}</div>
        <span className="fine" style={{ marginLeft: 8 }}>▾</span>
      </div>
      <div className="turns" ref={scroller}>
        {run.turns.map((t, i) => t.kind === 'tool'
          ? <div className="tool" key={i}><span style={{ color: 'var(--blue)' }}>{I.check}</span><span><b>{t.text}</b>{t.meta ? ` · ${t.meta}` : ''}</span><span className="s">{t.secs != null ? `${t.secs.toFixed(1)} s` : ''}</span></div>
          : <div className={`turn ${t.kind}`} key={i}><span className="av">{t.kind === 'you' ? 'R' : BRAND[0]}</span><span style={{ paddingTop: 3 }}>{t.text}</span></div>)}
        {onCall && <div className="thinking" style={{ paddingLeft: 34 }}><i/><i/><i/> waiting for you</div>}
      </div>
      <div className="sugg">{['What if Evergreen doesn’t pay?', 'Show me who’s late', 'Can I afford a hire in January?'].map(q => <button key={q} onClick={() => onAsk(q)}>{q}</button>)}</div>
      <div className="dinput"><input placeholder={`Ask ${BRAND} a follow-up, or just say it…`} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') send() }} /><button className="btn primary" style={{ height: 32, padding: '0 14px' }} onClick={send}>Ask</button></div>
      {browserVoice && <div className="browser-voice-control">
        <button className={`mic ${voiceStatus === 'listening' ? 'listening' : ''}`} type="button" aria-label={voiceStatus === 'listening' ? 'Listening for one follow-up' : 'Speak one follow-up'} aria-pressed={voiceStatus === 'listening'} disabled={voiceStatus === 'listening'} onClick={startVoiceFollowUp}>{I.mic} Speak follow-up</button>
        <span role={voiceStatus === 'error' ? 'alert' : 'status'} aria-live="polite">{voiceStatus === 'listening' ? 'Listening…' : voiceMessage}</span>
      </div>}
      {!live && <div className="controls" style={{ justifyContent: 'flex-end' }}>demo replay · <button onClick={() => onReplay(1)}>restart</button><button onClick={() => onReplay(3)}>3× speed</button><a href="?live">connect live</a></div>}
    </div>}
    {!open && preview && <div className="preview" onClick={() => setOpen(true)}><span className="av">{BRAND[0]}</span><span style={{ flex: 1 }}>{preview}</span><button className="x" aria-label="close" onClick={e => { e.stopPropagation(); setPreview(null) }}>×</button></div>}
    {!open && <button className="bubble" onClick={() => setOpen(true)}>
      <span className="ic green">{I.phone}</span>
      <div className={`wave ${onCall ? '' : 'idle'}`}>{Array.from({ length: 7 }).map((_, i) => <i key={i} style={{ height: 4 + ((i * 7) % 14) }} />)}</div>
      <b>{onCall ? `On a call · ${mm}` : 'Transcript'}</b>
      {run.turns.length > 0 && <span className="badge">{run.turns.length}</span>}
    </button>}
  </div>
}

/* ---------- app ---------- */
export default function App() {
  const [runs, setRuns] = useState<RunState[]>([])
  const [rootId, setRootId] = useState<string | undefined>(RUN || undefined)
  const [chatTitle, setChatTitle] = useState(() => RUN && readChatTitle(COMPANY, RUN) || 'General chat')
  const liveRef = useRef<ReturnType<typeof connectLive> | null>(null)
  const [editingChatTitle, setEditingChatTitle] = useState(false)
  const [chatTitleDraft, setChatTitleDraft] = useState(chatTitle)
  const cancelChatTitleEdit = useRef(false)
  const [elapsed, setElapsed] = useState(42)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [speed, setSpeed] = useState(SPEED)
  const stopRef = useRef<() => void>(() => {})
  const applyNow = (ev: RawEvent) => setRuns(prev => {
    const rid = ev.data?.run_id || ev.run_id || prev[prev.length - 1]?.run_id
    const idx = prev.findIndex(r => r.run_id === rid)
    if (ev.event === 'run.start' || idx < 0) return [...prev.filter(r => r.run_id !== rid), reduce(emptyRun(), ev)]
    const next = prev.slice(); next[idx] = reduce(prev[idx], ev); return next
  })
  // sequential presentation: never mount two nodes in the same instant, even if the backend bursts
  const queue = useRef<RawEvent[]>([]); const draining = useRef(false)
  const apply = (ev: RawEvent) => {
    if (BROWSER_VOICE) {
      const text = assistantSpeechText(ev)
      if (text && typeof window !== 'undefined' && 'speechSynthesis' in window) {
        try {
          const eventId = ev.data?.id == null ? undefined : String(ev.data.id)
          if (claimSpeechEvent(eventId, window.sessionStorage)) window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
        } catch { /* speech is an enhancement; the transcript remains available */ }
      }
    }
    queue.current.push(ev); if (!draining.current) drain()
  }
  const drain = async () => {
    draining.current = true
    while (queue.current.length) {
      const ev = queue.current.shift()!; applyNow(ev)
      const beat = ev.event === 'node.create' ? 420 : ev.event === 'decision' ? 250 : ev.event === 'speech' ? 150 : 0
      if (beat) await new Promise(r => setTimeout(r, beat))
    }
    draining.current = false
  }
  const playing = useRef(false)
  const play = async (s = speed) => { stopRef.current(); setRuns([]); playing.current = true; const stop = await playFixture('/fixture.json', apply, s); stopRef.current = () => { playing.current = false; stop() } }
  useEffect(() => {
    if (RUN || LIVE) {
      liveRef.current = connectLive(COMPANY, RUN, apply, e => setError(String(e)), STATIC, FRESH, id => {
        setRootId(id); setChatTitle(readChatTitle(COMPANY, id) || 'General chat')
        const url = new URL(location.href); url.searchParams.set('run', id); url.searchParams.delete('new'); history.replaceState(null, '', url)
      })
      return liveRef.current
    }
    if (!playing.current) play(); return () => stopRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (!BROWSER_VOICE || !('speechSynthesis' in window)) return
    const stopSpeech = () => window.speechSynthesis.cancel()
    window.addEventListener('pagehide', stopSpeech)
    return () => { window.removeEventListener('pagehide', stopSpeech); stopSpeech() }
  }, [])
  useEffect(() => { const t = setInterval(() => setElapsed(e => e + 1), 1000); return () => clearInterval(t) }, [])

  const onDecide = async (d: Decision, opt: string, selected?: string[]) => {
    try {
      if (LIVE) await resolveDecision(d.decision_id, opt, COMPANY, selected)
      apply({ event: 'decision.resolved', data: { decision_id: d.decision_id, option_id: opt, run_id: runs.find(r => r.decisions[d.decision_id])?.run_id } })
      setError('')
    } catch (e) { setError(String(e)) }
  }
  const followUp = async (q: string) => {
    setInput('')
    if (BROWSER_VOICE && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    if (LIVE) {
      const latest = runs[runs.length - 1]
      const pending = latest && Object.values(latest.decisions).filter(decision => !decision.resolved).slice(-1)[0]
      const optionId = pending && approvalChoice(q, pending.options)
      if (pending && optionId) {
        try {
          await resolveDecision(pending.decision_id, optionId, COMPANY)
          apply({ event: 'decision.resolved', data: { decision_id: pending.decision_id, option_id: optionId, run_id: latest.run_id } })
          setError('')
        } catch (e) { setError(String(e)) }
        return
      }
    }
    if (LIVE) {
      try {
        const parent = runs[runs.length - 1]
        const created = await startRun(COMPANY, q, BROWSER_VOICE ? 'call' : 'web', parent?.run_id)
        if (!parent) await liveRef.current?.watch(created.run_id)
        setError('')
      } catch (e) { setError(String(e)) }
      return
    }
    // demo: synthesize a follow-up branch from the current run
    const base = BROWSER_VOICE ? runs[runs.length - 1] : runs[0]; if (!base) return
    const ctx = Object.values(base.nodes).find(n => n.type === 'context'), fc = Object.values(base.nodes).find(n => n.type === 'forecast')
    const rid = 'run-follow-' + Date.now(); const now = Date.now()
    const drop = 1156.04
    const evs: RawEvent[] = [
      { event: 'run.start', data: { run_id: rid, question: q, source: 'web', company_id: COMPANY } },
      { event: 'node.create', data: { run_id: rid, node_id: 'f1', type: 'context', title: 'Pulling up context', status: 'done', parent: null, data: { ...ctx?.data } } },
      { event: 'node.create', data: { run_id: rid, node_id: 'f3', type: 'forecast', title: 'Forecasting without Evergreen', status: 'running', parent: 'f1' } },
      { event: 'node.update', data: { run_id: rid, node_id: 'f3', status: 'done', data: { ...fc?.data, expected_by_target: (fc?.data.expected_by_target || 0) - drop, cash_at_target: (fc?.data.cash_at_target || 0) - drop, gap: Math.max(0, drop - (fc?.data.cash_at_target || 0)) } } },
      { event: 'node.create', data: { run_id: rid, node_id: 'f4', type: 'answer', title: 'Short.', status: 'done', parent: 'f3', data: { answer: 'no', gap: Math.max(0, drop - (fc?.data.cash_at_target || 0)) } } },
      { event: 'speech', data: { run_id: rid, text: `If Evergreen doesn’t pay, you’d be about $${Math.round(drop - (fc?.data.cash_at_target || 0)).toLocaleString()} short on the twentieth. Two things would cover it.` } },
      { event: 'node.create', data: { run_id: rid, node_id: 'f5', type: 'levers', title: 'What covers it', status: 'done', parent: 'f4', data: { recommended: ['chase'], levers: [
        { id: 'chase', label: 'Also text Yeoman Roasters', recovers: 669.12, targets: [{ customer_id: 'c50', customer: 'Yeoman Roasters Co.', amount: 669.12 }] },
      ] } } },
      { event: 'decision', data: { run_id: rid, decision_id: 'd-follow', node_id: 'f5', prompt: 'Text Yeoman Roasters?', options: [{ id: 'yes', label: 'Yes, text Yeoman' }, { id: 'no', label: 'Not now' }], auto_resolves_in_s: null } },
    ]
    let t = 0; for (const e of evs) { t += 650; setTimeout(() => apply({ ...e, data: { ...e.data, ts: now } }), t) }
  }
  // ask the backend for the one-page report once a run has ended without one (live/planner runs)
  const asked = useRef<Set<string>>(new Set())
  const [reportFailed, setReportFailed] = useState<Record<string, boolean>>({})
  useEffect(() => {
    if (!LIVE && !RUN) return
    for (const r of runs) {
      if (r.status !== 'closed' || r.report_id || asked.current.has(r.run_id)) continue
      if (Object.values(r.nodes).some(node => node.type === 'answer' && node.data.awaiting_input)) continue
      asked.current.add(r.run_id)
      generateReport(r.run_id, COMPANY).then(res => {
        if (res?.report_id) apply({ event: 'report.ready', data: { run_id: r.run_id, report_id: res.report_id } })
        else setReportFailed(f => ({ ...f, [r.run_id]: true }))
      }).catch(() => setReportFailed(f => ({ ...f, [r.run_id]: true })))
    }
  }, [runs])
  const retryReport = (r: RunState) => { asked.current.delete(r.run_id); setReportFailed(f => ({ ...f, [r.run_id]: false })); setRuns(x => x.slice()) }
  const saveChatTitle = () => {
    if (cancelChatTitleEdit.current) {
      cancelChatTitleEdit.current = false
      return
    }
    const title = chatTitleDraft.trim() || 'General chat'
    setChatTitle(title)
    if (rootId) writeChatTitle(COMPANY, rootId, title)
    setEditingChatTitle(false)
  }
  const main = BROWSER_VOICE ? runs[runs.length - 1] : runs[0]
  return <div className="app">
    <header className="topbar">
      <div className="brand"><img className="mark" src="/logo.png" alt="" /><div className="name">{BRAND.toLowerCase()}</div></div>
      <div className="company">Palletbay Storage &amp; Warehousing</div>
      <div className="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg><input autoFocus={FRESH} aria-label="Ask Span" placeholder="Ask about your money, or search transactions, customers, reports" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && input.trim()) followUp(input.trim()) }} /></div>
      <div className="status"><i className="dot" />{BROWSER_VOICE ? 'Browser voice demo' : main?.status === 'open' ? 'On a call' : LIVE ? 'Live' : 'Demo replay'}</div>
    </header>
    <div className="body">
      <nav className="rail">
        <a className="on" href="/">{I.chat}Ask</a><a href="/home">{I.book}Home</a><a href={`/get-paid${COMPANY !== 'company-020' ? `?company=${encodeURIComponent(COMPANY)}` : ''}`}>{I.card}Get paid</a><a href={`/reports${COMPANY !== 'company-020' ? `?company=${encodeURIComponent(COMPANY)}` : ''}`}>{I.trend}Reports</a><a href={`/customers${COMPANY !== 'company-020' ? `?company=${encodeURIComponent(COMPANY)}` : ''}`}>{I.person}Customers</a>
      </nav>
      {LIVE && <ChatSidebar company={COMPANY} active={rootId} revision={`${runs.length}:${runs.map(r => r.status).join()}:${chatTitle}`} onRename={(id, title) => { if (id === rootId) setChatTitle(title) }} />}
      <main className="main">
        {error && <div role="alert">{error}</div>}
        {main ? <>
          <div className="eyebrow"><span className="av">R</span><span>Ryan · {BROWSER_VOICE && main.source === 'call' ? 'via browser voice' : main.source === 'call' ? 'by phone' : main.source} · Sat 3:52 PM</span><span className="sep" /><span>Thread 1 of 3 today</span><span className="sep" /><span className="link">Through Oct 20</span></div>
          {editingChatTitle
            ? <input
                autoFocus
                aria-label="Rename chat"
                className="chat-title-input"
                value={chatTitleDraft}
                onChange={e => setChatTitleDraft(e.target.value)}
                onBlur={saveChatTitle}
                onKeyDown={e => {
                  if (e.key === 'Enter') saveChatTitle()
                  if (e.key === 'Escape') {
                    cancelChatTitleEdit.current = true
                    setChatTitleDraft(chatTitle)
                    setEditingChatTitle(false)
                  }
                }}
              />
            : <h1
                className="q"
                title="Double-click to rename"
                tabIndex={0}
                onDoubleClick={() => { setChatTitleDraft(chatTitle); setEditingChatTitle(true) }}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === 'F2') { setChatTitleDraft(chatTitle); setEditingChatTitle(true) }
                }}
              >{chatTitle}</h1>}
        </> : <div className="empty-chat"><h1 className="q">General chat</h1><p>{FRESH ? "Ask a question about your books to start a new conversation." : "Connecting…"}</p></div>}
        {runs.map(r => <div key={r.run_id} id={`thread-${r.run_id}`} data-run-id={r.run_id}>
          {isPlannerRun(r)
            ? <PlannerThread run={r} parent={runs.find(p => p.run_id === r.parent_run_id)} onDecide={onDecide} reportFailedFor={x => !!reportFailed[x.run_id]} retryReportFor={retryReport} />
            : <Thread run={r} onDecide={onDecide} isFollowUp={!!r.parent_run_id} parent={runs.find(p => p.run_id === r.parent_run_id)} reportFailedFor={x => !!reportFailed[x.run_id]} retryReportFor={retryReport} />}
        </div>)}
      </main>
    </div>
    {main && <Dock run={main} elapsed={elapsed} input={input} setInput={setInput} onAsk={followUp} live={LIVE} onReplay={(sp) => { setSpeed(sp); play(sp) }} browserVoice={BROWSER_VOICE} />}
  </div>
}
