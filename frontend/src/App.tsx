import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Decision, GraphNode, Lever, RawEvent, RunState } from './types'
import { emptyRun, k, money, reduce } from './events'
import { playFixture, resolveDecision, startRun, subscribe } from './api'
import DailyCashChart from './DailyCashChart'

const COMPANY = 'company-020'
const BRAND = (import.meta.env.VITE_BRAND as string) || 'Owed'
const LIVE = new URLSearchParams(location.search).has('live')
const SPEED = Number(new URLSearchParams(location.search).get('speed') || 1)

/* ---------- icons ---------- */
const I = {
  book: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="4" width="11" height="8.5" rx="1"/><path d="M2.5 7h11"/></svg>,
  people: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="6" cy="5.5" r="2.5"/><path d="M1.5 13c.8-3 2.6-4 4.5-4s3.7 1 4.5 4M11 6l1.3 1.3L14.5 5"/></svg>,
  trend: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2.5 12.5 6 8l3 2.5 4.5-6"/></svg>,
  chat: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/></svg>,
  cal: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="3.5" width="11" height="10" rx="1"/><path d="M2.5 7h11M5.5 2v3M10.5 2v3"/></svg>,
  person: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="8" cy="5.5" r="2.5"/><path d="M3 14c.8-3 2.6-4 5-4s4.2 1 5 4"/></svg>,
  phone: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3.5 2.5h2.5l1.2 3-1.6 1a8 8 0 0 0 4 4l1-1.6 3 1.2v2.5a1.5 1.5 0 0 1-1.6 1.5A11.5 11.5 0 0 1 2 4.1 1.5 1.5 0 0 1 3.5 2.5z"/></svg>,
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
  const gap = fc?.data.gap ?? n.data.gap ?? 0; const need = fc?.data.need ?? 0; const cushion = fc ? (fc.data.cash_at_target ?? 0) - need : -gap
  const risk = fc?.data.pessimistic?.gap
  const cls = cushion < 0 ? 'bad' : cushion < need * 0.1 ? '' : 'ok'
  const word = cushion < 0 ? 'No.' : cushion < need * 0.1 ? 'Barely.' : 'Yes.'
  return <div className={`node verdict ${cls}`} style={{ width: 270 }}>
    <Gauge cushion={cushion} need={need} />
    <div className="big">{word}</div>
    <div className="sub">{cushion < 0 ? `${money(-cushion)} short` : `${money(cushion)} to spare`}</div>
    <div className="fine">{risk > 0 ? `${money(risk)} short if the slow payers slip` : cushion < 0 ? 'even if the usual payers pay' : 'covered even if the slow payers slip'}</div>
  </div>
}
function LeverCard({ l, rec, decision, onChoose, chosen }: { l: Lever; rec: boolean; decision?: Decision; onChoose: (opt: string) => void; chosen?: string }) {
  const icon = l.id === 'chase' ? I.chat : l.id === 'defer_bill' ? I.cal : I.person
  const zero = !l.recovers
  const primary = decision?.options.find(o => o.id === 'yes') || decision?.options[0]
  return <div className={`lever ${rec ? 'rec' : ''} ${zero ? 'dim' : ''}`}>
    <div>
      <div className="head"><b><span className={`ic ${rec ? 'green' : 'grey'}`}>{icon}</span>{l.label}</b><span className="amt" style={zero ? { color: 'var(--muted2)' } : undefined}>+ {money(l.recovers)}</span></div>
      {l.targets && <div className="chips" style={{ marginTop: 10 }}>{l.targets.map((t, i) => <span className="chip" key={t.customer_id}><span className="av" style={{ background: AV_COLORS[i % 5] }}>{initials(t.customer)}</span>{money(t.amount)}</span>)}</div>}
      {l.bills && <div className="chips" style={{ marginTop: 10 }}>{l.bills.map(b => <span className="chip plain" key={b.bill_id}>{b.vendor} · {money(b.amount)}</span>)}</div>}
      <div className="fine" style={{ marginTop: 10, display: 'flex', gap: 6, alignItems: 'center' }}>
        {l.targets && <><i className="dot" />all usually pay within a week of a nudge</>}
        {l.bills && <><i className="dot" />both have taken late payment before, no fee</>}
        {zero && 'Nothing scheduled this month, so nothing to hold.'}
      </div>
    </div>
    {rec && primary ? (
      chosen ? <button className="btn done" disabled>{I.check} {chosen === 'no' ? 'Not now' : 'Texting them'}</button>
        : <div style={{ display: 'flex', gap: 8 }}><button className="btn primary" onClick={() => onChoose(primary.id)}>{primary.label}</button>{decision!.options.filter(o => o.id !== primary.id).slice(0, 1).map(o => <button key={o.id} className="btn" onClick={() => onChoose(o.id)}>{o.label}</button>)}</div>
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
function buildSeries(ctx?: GraphNode, sc?: GraphNode, fc?: GraphNode) {
  const bank = ctx?.data.bank_balance ?? 0
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
  return { good: walk(inflowGood), bad: walk(inflowBad), days, target, pay, bank }
}
function CashChart({ ctx, sc, fc }: { ctx?: GraphNode; sc?: GraphNode; fc?: GraphNode }) {
  const W = 760, H = 200, base = 156, top = 14
  const { good, bad, days, target, pay, bank } = useMemo(() => buildSeries(ctx, sc, fc), [ctx, sc, fc])
  const step = W / days, mid = Math.floor(days / 2)
  const maxV = Math.max(...good, 1) * 1.08, minV = Math.min(...bad, 0)
  const y = (v: number) => base - ((v - minV) / (maxV - minV)) * (base - top)
  const path = (pts: number[]) => pts.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const endG = good[days], endB = bad[days]
  return <div className="chart card">
    <div className="head"><b>Cash in the bank, day by day</b><div className="legend"><span><i style={{ width: 14, height: 3, borderRadius: 2, background: 'var(--green)' }} />usual payers pay</span><span><i style={{ width: 14, height: 3, borderRadius: 2, background: 'var(--amber)' }} />slow payers slip</span></div></div>
    <svg viewBox={`0 0 ${W} ${H}`} fill="none">
      <path d={`${path(good)} L${W} ${y(0)} L0 ${y(0)} Z`} fill="#2CA01C" fillOpacity=".10" />
      <path d={`M0 ${y(0)} H${W}`} stroke="#D52B1E" strokeWidth="1.5" strokeDasharray="4 4" />
      <path d={path(bad)} stroke="#E08A00" strokeWidth="2" strokeDasharray="5 4" strokeLinejoin="round" />
      <path d={path(good)} stroke="#2CA01C" strokeWidth="2.5" strokeLinejoin="round" />
      <path d={`M${mid * step} ${top} V${base} M${W - 1} ${top} V${base}`} stroke="#8D9096" strokeWidth="1" strokeDasharray="3 4" />
      <circle cx={W - 2} cy={y(endG)} r="5" fill="#fff" stroke="#2CA01C" strokeWidth="2.5" /><circle cx={W - 2} cy={y(endB)} r="5" fill="#fff" stroke="#E08A00" strokeWidth="2" />
      <text x="0" y={H - 6} fontSize="11" fill="#6B6C72">Today · ${k(bank)}</text>
      <text x={mid * step} y={H - 6} fontSize="11" fontWeight="600" fill="#393A3D" textAnchor="middle">{fmtDate(shift(target, -7))} · payday</text>
      <text x={W - 4} y={H - 6} fontSize="11" fontWeight="600" fill="#393A3D" textAnchor="end">{fmtDate(target)} · payday</text>
      <text x={W - 12} y={Math.min(y(endG), y(endB) - 16) - 8} fontSize="12" fontWeight="700" fill="#2CA01C" textAnchor="end">{endG >= 0 ? '+' : '−'}${k(Math.abs(endG))}</text>
      <text x={W - 12} y={Math.max(y(endB), y(endG) + 16) + 16} fontSize="12" fontWeight="700" fill="#B35C00" textAnchor="end">{endB >= 0 ? '+' : '−'}${k(Math.abs(endB))}</text>
      <text x={mid * step + 8} y="26" fontSize="11" fill="#6B6C72">− ${k(pay / 2)} payroll</text>
    </svg>
  </div>
}
function Outcome({ fc, payments, levers }: { fc?: GraphNode; payments: GraphNode[]; levers: Lever[] }) {
  const now = fc?.data.cash_at_target ?? 0, got = payments.reduce((a, p) => a + (p.data.amount || 0), 0), before = now - got
  const need = fc?.data.need || 1
  const Bar = ({ v, c, label }: { v: number; c: string; label: string }) => <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><div className="kv"><span style={{ color: 'var(--muted)' }}>{label}</span><b style={{ color: v < 0 ? 'var(--red)' : undefined }}>{v < 0 ? '−' : '+'}{money(Math.abs(v))}</b></div><div className="bar"><i style={{ width: `${Math.min(100, Math.max(2, 100 * Math.abs(v) / (need * 0.3)))}%`, background: c }} /></div></div>
  return <div className="card outcome">
    <b style={{ fontSize: 14 }}>Where you stand now</b>
    <Bar v={before} c="var(--amber)" label="Cushion when you asked" />
    <Bar v={now} c={now >= 0 ? 'var(--green)' : 'var(--red)'} label="Cushion now" />
    {payments.length > 0 && <div className="fine" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span className="ic green" style={{ width: 18, height: 18 }}>{I.check}</span>{payments.length} payment{payments.length > 1 ? 's' : ''} landed · {money(got)}</div>}
    {levers.length > 0 && <div className="fine">Still on the table: {levers.filter(l => l.recovers).map(l => `${l.label} (+${money(l.recovers)})`).join(' · ')}</div>}
  </div>
}
const shift = (d?: string, days = 0) => { if (!d) return undefined; const t = new Date(d + 'T00:00:00'); t.setDate(t.getDate() + days); return t.toISOString().slice(0, 10) }

function whoOf(n: GraphNode): string {
  const t = n.title || ''
  const m = t.match(/^Texting (.+)$/) || t.match(/^Negotiating with (.+?)['’]s agent$/) || t.match(/^(.+?) replied$/) || t.match(/^(.+?) paid /)
  return (m ? m[1] : t).split(' ')[0]
}
function Conversations({ actions }: { actions: GraphNode[] }) {
  const groups = new Map<string, GraphNode[]>()
  for (const a of actions) { const w = whoOf(a); groups.set(w, [...(groups.get(w) || []), a]) }
  if (!groups.size) return null
  return <div className="convs">
    {[...groups.entries()].map(([who, items], gi) => {
      const full = items.find(i => i.data.kind === 'reminder')?.title.replace(/^Texting /, '') || who
      return <div className="conv" key={who}>
        <div className="chead"><span className="av" style={{ background: AV_COLORS[gi % 5] }}>{initials(full)}</span><div><b>{full}</b><div className="fine">SMS · pay link included</div></div></div>
        <div className="bubbles">
          {items.map(a => {
            const d = a.data
            if (d.kind === 'reminder') return <div key={a.node_id} className="bub out"><div>{String(d.draft?.body || a.title).replace('{pay_link}', 'owed.co/p/8f3a')}</div><span className="meta">{BRAND} for Palletbay · {a.status === 'done' ? 'delivered' : 'sending…'}</span></div>
            if (d.kind === 'reply') return <div key={a.node_id} className="bub in"><div>{d.text}</div><span className="meta">{who} · read by {BRAND} · {String(d.classification || '').replace('_', ' ')}</span></div>
            if (d.kind === 'negotiation') return <div key={a.node_id} className="neg">
              <div className="fine" style={{ textAlign: 'center' }}>{BRAND} is negotiating with {who}’s agent{a.status === 'running' ? '…' : ''}</div>
              {a.rounds.map((r, i) => <div key={i} className={`bub ${r.from === 'owed' ? 'out agent' : 'in agent'}`}><div>{r.text}</div><span className="meta">{r.from === 'owed' ? `${BRAND} agent` : `${who}’s agent`}{r.p_honored ? ` · ${Math.round(r.p_honored * 100)}% likely honored` : ''}</span></div>)}
              {d.agreement && <div className="agree">{I.check} Agreed: {d.agreement.installments?.length} payments of {money(d.agreement.installments?.[0]?.amount)}</div>}
            </div>
            if (d.kind === 'payment') return <div key={a.node_id} className="receipt"><span className="ic green">{I.card}</span><div><b>{money(d.amount)} received</b><div className="fine">{String(d.rail).toUpperCase()} · card ending {d.receipt?.last4}</div></div></div>
            return <div key={a.node_id} className="fine">{a.title}</div>
          })}
        </div>
      </div>
    })}
  </div>
}

/* ---------- a thread = one run ---------- */
function Thread({ run, onDecide, isFollowUp }: { run: RunState; onDecide: (d: Decision, opt: string) => void; isFollowUp?: boolean }) {
  const byType = (t: string) => run.order.map(id => run.nodes[id]).find(n => n.type === t)
  const ctx = byType('context'), sc = byType('scoring'), fc = byType('forecast'), ans = byType('answer'), lv = byType('levers')
  const actions = run.order.map(id => run.nodes[id]).filter(n => n.type === 'action')
  const levers: Lever[] = lv?.data.levers || []
  const decision = Object.values(run.decisions).find(d => d.node_id === lv?.node_id)
  const chosen = decision?.resolved
  const verdictRef = useRef<HTMLDivElement | null>(null), contRef = useRef<HTMLDivElement | null>(null)
  const leverRefs = useMemo(() => levers.map(() => ({ current: null as HTMLDivElement | null })), [levers.length])
  return <section className="thread" ref={contRef}>
    {isFollowUp && <div className="branch"><span className="ic grey" style={{ width: 20, height: 20 }}>{I.chat}</span>Follow-up · branches from this run</div>}
    {isFollowUp && <h1 className="q" style={{ fontSize: 22, lineHeight: '28px', marginBottom: 14 }}>{run.question}</h1>}
    <div className="flow">
      {ctx && <BooksNode n={ctx} />}
      {sc && <><div className="arrow">{I.arrow}</div><ScoredNode n={sc} /></>}
      {fc && <><div className="arrow">{I.arrow}</div><CashNode n={fc} ctx={ctx} /></>}
      {ans && <><div className="arrow">{I.arrow}</div><div ref={verdictRef} style={{ display: 'flex' }}><VerdictNode n={ans} fc={fc} /></div></>}
    </div>
    {levers.length > 0 && <>
      <Fork fromRef={verdictRef} toRefs={leverRefs} containerRef={contRef} />
      <div className="levers">{levers.map((l, i) => <div key={l.id} ref={el => { leverRefs[i].current = el }} style={{ flex: 1, display: 'flex' }}><LeverCard l={l} rec={(lv?.data.recommended || ['chase'])[0] === l.id} decision={decision} chosen={chosen} onChoose={opt => decision && onDecide(decision, opt)} /></div>)}</div>
    </>}
    {lv && levers.length === 0 && <div className="thinking" style={{ marginTop: 16 }}><i/><i/><i/> working out what would close the gap</div>}
    {actions.length > 0 && <Conversations actions={actions} />}
    {fc && fc.status === 'done' && <div className="split">{LIVE ? <DailyCashChart company={run.company_id || COMPANY} target={fc.data.target_date || ctx?.data.target_date || ctx?.data.payroll_date} revision={fc.data.cash_at_target} neverPays={fc.data.excluded_customer_id} /> : <CashChart ctx={ctx} sc={sc} fc={fc} />}<Outcome fc={fc} payments={actions.filter(a => a.data.kind === 'payment')} levers={levers} /></div>}
  </section>
}

/* ---------- bottom-right dock: call transcript + chat ---------- */
function Dock({ run, elapsed, input, setInput, onAsk, live, onReplay }: { run: RunState; elapsed: number; input: string; setInput: (s: string) => void; onAsk: (q: string) => void; live: boolean; onReplay: (speed: number) => void }) {
  const [open, setOpen] = useState(false)
  const onCall = run.status === 'open'
  const lastOwed = [...run.turns].reverse().find(t => t.kind === 'owed')
  const [preview, setPreview] = useState<string | null>(null)
  useEffect(() => { if (!open && lastOwed) { setPreview(lastOwed.text); const t = setTimeout(() => setPreview(null), 6000); return () => clearTimeout(t) } }, [lastOwed?.text, open])
  const mm = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`
  const scroller = useRef<HTMLDivElement | null>(null)
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' }) }, [run.turns.length, open])
  const send = () => { const q = input.trim(); if (q) onAsk(q) }
  return <div className={`dock ${open ? 'open' : ''}`}>
    {open && <div className="dpanel">
      <div className="dhead" onClick={() => setOpen(false)}>
        <span className="ic green">{I.phone}</span>
        <div style={{ flex: 1 }}><b>{onCall ? `On a call · ${mm}` : 'Call ended'}</b><div className="fine">{onCall ? 'Listening · tool rows show what ' + BRAND + ' did between sentences' : 'Transcript saved'}</div></div>
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
      {!live && <div className="controls" style={{ justifyContent: 'flex-end' }}>demo · <button onClick={() => onReplay(1)}>replay</button><button onClick={() => onReplay(3)}>3×</button><a href="?live" style={{ color: 'var(--blue)' }}>go live</a></div>}
    </div>}
    {!open && preview && <div className="preview" onClick={() => setOpen(true)}><span className="av">{BRAND[0]}</span><span>{preview}</span></div>}
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
  const [elapsed, setElapsed] = useState(42)
  const [input, setInput] = useState('')
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
  const apply = (ev: RawEvent) => { queue.current.push(ev); if (!draining.current) drain() }
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
    if (LIVE) { const off = subscribe(COMPANY, apply); startRun(COMPANY, 'Am I going to make payroll these next two weeks?').catch(() => {}); return off }
    if (!playing.current) play(); return () => stopRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { const t = setInterval(() => setElapsed(e => e + 1), 1000); return () => clearInterval(t) }, [])

  const onDecide = async (d: Decision, opt: string) => {
    apply({ event: 'decision.resolved', data: { decision_id: d.decision_id, option_id: opt, run_id: runs.find(r => r.decisions[d.decision_id])?.run_id } })
    if (LIVE) await resolveDecision(d.decision_id, opt, COMPANY).catch(() => {})
  }
  const followUp = async (q: string) => {
    setInput('')
    if (LIVE) { await startRun(COMPANY, q); return }
    // demo: synthesize a follow-up branch from the current run
    const base = runs[0]; if (!base) return
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
        { id: 'defer_bill', label: 'Slide the Utilities bill', recovers: 322, bills: [{ bill_id: 'b1', vendor: 'Utilities', amount: 322, due_date: '2026-10-15' }] },
      ] } } },
      { event: 'decision', data: { run_id: rid, decision_id: 'd-follow', node_id: 'f5', prompt: 'Approve?', options: [{ id: 'yes', label: 'Approve both' }, { id: 'no', label: 'Not now' }], auto_resolves_in_s: null } },
    ]
    let t = 0; for (const e of evs) { t += 650; setTimeout(() => apply({ ...e, data: { ...e.data, ts: now } }), t) }
  }
  const main = runs[0]
  return <div className="app">
    <header className="topbar">
      <div className="brand"><div className="mark">{BRAND[0]}</div><div className="name">{BRAND.toLowerCase()}</div></div>
      <div className="company">Palletbay Storage &amp; Warehousing</div>
      <div className="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg><input placeholder="Ask about your money, or search transactions, customers, reports" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && input.trim()) followUp(input.trim()) }} /></div>
      <div className="status"><i className="dot" />{main?.status === 'open' ? 'On a call' : LIVE ? 'Live' : 'Demo replay'}</div>
    </header>
    <div className="body">
      <nav className="rail">
        <a className="on">{I.chat}Ask</a><a>{I.book}Home</a><a>{I.card}Get paid</a><a>{I.trend}Reports</a><a>{I.person}Customers</a>
      </nav>
      <main className="main">
        {main ? <>
          <div className="eyebrow"><span className="av">R</span><span>Ryan · by {main.source === 'call' ? 'phone' : main.source} · Sat 3:52 PM</span><span className="sep" /><span>Thread 1 of 3 today</span><span className="sep" /><span className="link">Through Oct 20</span></div>
          <h1 className="q">{main.question}</h1>
        </> : <div className="thinking"><i/><i/><i/> connecting</div>}
        {runs.map((r, i) => <Thread key={r.run_id} run={r} onDecide={onDecide} isFollowUp={i > 0} />)}
      </main>
    </div>
    {main && <Dock run={main} elapsed={elapsed} input={input} setInput={setInput} onAsk={followUp} live={LIVE} onReplay={(sp) => { setSpeed(sp); play(sp) }} />}
  </div>
}
