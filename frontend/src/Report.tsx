import { Fragment, useCallback, useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import type { ReportDoc, ReportNode } from './types'
import { getReport } from './api'
import { money } from './events'

const BRAND = (import.meta.env.VITE_BRAND as string) || 'Owed'

const I = {
  dl: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M8 2.5v7M4.8 6.8 8 10l3.2-3.2M2.5 13.5h11"/></svg>,
  print: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4.5 6V2.5h7V6M4.5 11.5H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v3.5a1 1 0 0 1-1 1h-1.5M4.5 9.5h7v4h-7z"/></svg>,
  book: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="4" width="11" height="8.5" rx="1"/><path d="M2.5 7h11"/></svg>,
  people: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="6" cy="5.5" r="2.5"/><path d="M1.5 13c.8-3 2.6-4 4.5-4s3.7 1 4.5 4M11 6l1.3 1.3L14.5 5"/></svg>,
  trend: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2.5 12.5 6 8l3 2.5 4.5-6"/></svg>,
  chat: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/></svg>,
  card: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M2 7.5h12M5 11h3"/></svg>,
  flag: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3.5 2.5v11M3.5 3h9l-2.2 3 2.2 3h-9"/></svg>,
  sliders: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2.5 5h7M12.5 5h1M2.5 11h3M8.5 11h5"/><circle cx="10.5" cy="5" r="1.8"/><circle cx="6.5" cy="11" r="1.8"/></svg>,
  box: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/></svg>,
  arrow: <svg width="18" height="10" viewBox="0 0 24 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M0 6h20M16 2l4 4-4 4"/></svg>,
}

const NODE_ICON: Record<string, ReactElement> = {
  context: I.book, scoring: I.people, forecast: I.trend, answer: I.flag, levers: I.sliders, action: I.chat,
}
const KIND_ICON: Record<string, { ic: ReactElement; cls: string }> = {
  reminder: { ic: I.chat, cls: 'grey' }, reply: { ic: I.chat, cls: 'blue' },
  negotiation: { ic: I.people, cls: 'amber' }, payment: { ic: I.card, cls: 'green' },
}
const fmtGen = (s: string) => {
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
const fmtTime = (s?: string) => {
  if (!s) return ''
  const d = new Date(s)
  return isNaN(d.getTime()) ? '' : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function status(r: ReportDoc): { label: string; cls: 'ok' | 'tight' | 'short' } {
  const gap = r.numbers.gap_now ?? r.numbers.gap_then ?? 0
  if (gap > 0) return { label: 'Short', cls: 'short' }
  const cushion = -gap, need = r.numbers.payroll || 0
  return cushion < need * 0.05 ? { label: 'Tight', cls: 'tight' } : { label: 'Covered', cls: 'ok' }
}

function NodeStrip({ nodes }: { nodes: ReportNode[] }) {
  return <div className="steps">
    {nodes.map((n, i) => <Fragment key={n.id}>
      {i > 0 && <span className="step-arrow">{I.arrow}</span>}
      <span className="step">
        <span className={`ic ${n.type === 'answer' ? 'amber' : 'grey'}`} style={{ width: 22, height: 22 }}>{NODE_ICON[n.type] || I.flag}</span>
        <span>{n.title}<em className="fine"> · {n.status}</em></span>
      </span>
    </Fragment>)}
  </div>
}

function DidRow({ n }: { n: ReportNode }) {
  const d = n.data, kind = d.kind || 'reminder'
  const { ic, cls } = KIND_ICON[kind] || KIND_ICON.reminder
  const when = fmtTime(d.sent_at || d.receipt?.paid_at)
  return <div className="did">
    <span className={`ic ${cls}`}>{ic}</span>
    <div style={{ minWidth: 0, flex: 1 }}>
      <div className="t">{n.title}{when && <span className="when">{when}</span>}</div>
      {kind === 'reminder' && d.draft && <div className="d">“{String(d.draft.body).replace('{pay_link}', 'pay link').slice(0, 160)}{String(d.draft.body).length > 160 ? '…' : ''}”{d.pay_link ? ' · pay link sent' : ''}</div>}
      {kind === 'reply' && <div className="d">“{d.text}”{d.classification ? ` · ${String(d.classification).replace('_', ' ')}` : ''}</div>}
      {kind === 'negotiation' && <div className="rounds">
        {(d.rounds || []).map((r: any, i: number) => <div className="r" key={i}><b>{r.from === 'owed' ? BRAND : 'them'}</b><span>{r.text}</span></div>)}
        {d.agreement && <div className="r"><b>agreed</b><span>{d.agreement.installments?.length} payments of {money(d.agreement.installments?.[0]?.amount)}</span></div>}
      </div>}
      {kind === 'payment' && <div className="d">{money(d.amount)} via {d.rail}{d.receipt?.last4 ? ` · card ending ${d.receipt.last4}` : ''}</div>}
    </div>
    <span className={`tag ${n.status}`}>{n.status}</span>
  </div>
}

export default function Report({ id }: { id: string }) {
  const [r, setR] = useState<ReportDoc | null>(null)
  const [err, setErr] = useState(false)
  const load = useCallback(() => {
    getReport(id).then(setR).catch(() => setErr(true))
  }, [id])
  useEffect(() => { load() }, [load])
  const retry = () => { setErr(false); load() }

  if (err) return <div className="report-wrap"><div className="sheet center">
    <div className="r-title" style={{ fontSize: 22 }}>Report not ready yet</div>
    <p className="fine" style={{ marginTop: 8 }}>The report may still be generating, or <code>{id}</code> doesn’t exist.</p>
    <div style={{ marginTop: 18, display: 'flex', gap: 10, justifyContent: 'center' }}>
      <button className="btn primary" onClick={retry}>Retry</button>
      <a className="btn" href="/">Back to canvas</a>
    </div>
  </div></div>
  if (!r) return <div className="report-wrap"><div className="sheet center"><div className="thinking"><i /><i /><i /> loading report</div></div></div>

  const st = status(r)
  const fc = r.workflow.nodes.find(n => n.type === 'forecast')?.data || {}
  const bills = fc.bills_due_by_target
  const gapT = r.numbers.gap_then, gapN = r.numbers.gap_now
  const acts = r.workflow.nodes.filter(n => n.type === 'action')
  const stats: { l: string; v?: number; sub?: string; hot?: boolean }[] = [
    { l: 'In the bank', v: r.numbers.bank_balance },
    { l: 'Payroll', v: r.numbers.payroll },
    { l: 'Bills due first', v: bills },
    { l: 'Customers owe', v: r.numbers.owed },
    { l: 'Expected in time', v: r.numbers.expected_by_target },
    { l: 'Cushion', v: gapN == null ? undefined : -gapN, sub: gapT != null && gapN != null && gapT !== gapN ? `was ${(gapT > 0 ? '−$' : '$') + Math.round(Math.abs(gapT)).toLocaleString()} when asked` : 'at the time of asking', hot: true },
  ]
  return <div className="report-wrap"><div className="sheet">
    <header className="rhead">
      <a className="rbrand" href="/"><span className="mark">{BRAND[0]}</span><span className="name">{BRAND.toLowerCase()}</span></a>
      <span className="rco">{r.company}</span>
      <span className="fine rgen">Generated {fmtGen(r.generated_at)}</span>
      <span className="noprint" style={{ display: 'flex', gap: 8 }}>
        <a className="btn" href={`/api/reports/${encodeURIComponent(r.report_id)}.pdf`}>{I.dl}Download PDF</a>
        <button className="btn primary" onClick={() => window.print()}>{I.print}Print</button>
      </span>
    </header>

    <div className="eyebrow" style={{ marginTop: 22 }}><span>{r.question ? 'One-page report' : 'Report'}</span><span className="sep" /><span>{r.run_id}</span></div>
    <h1 className="q" style={{ paddingRight: 0, marginBottom: 10 }}>{r.question}</h1>
    <div className="r-ansrow">
      <div className="r-title">{r.answer}</div>
      <span className={`spill ${st.cls}`}>{st.label}</span>
    </div>

    <h2 className="rsec">Numbers used</h2>
    <div className="stats">
      {stats.map(s => <div className="stat" key={s.l}>
        <div className="sl">{s.l}</div>
        <div className="sv" style={s.hot ? { color: (s.v ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' } : undefined}>
          {s.v == null ? '—' : (s.v < 0 ? '−$' : '$') + Math.round(Math.abs(s.v)).toLocaleString()}
        </div>
        {s.sub && <div className="fine">{s.sub}</div>}
      </div>)}
    </div>

    <h2 className="rsec">How I got there</h2>
    {r.workflow.svg
      ? <div className="wflow" dangerouslySetInnerHTML={{ __html: r.workflow.svg }} />
      : <NodeStrip nodes={r.workflow.nodes} />}

    <h2 className="rsec">What I did</h2>
    {acts.length > 0
      ? <div className="dids">{acts.map(n => <DidRow key={n.id} n={n} />)}</div>
      : r.actions.length > 0
        ? <ul className="plain">{r.actions.map((a, i) => <li key={i}><b>{a.title}</b> — {a.result}</li>)}</ul>
        : <div className="fine">Nothing yet.</div>}

    <h2 className="rsec">Still open</h2>
    {r.open_items.length > 0
      ? <ul className="open">{r.open_items.map((o, i) => <li key={i}><span className="chk">{I.box}</span>{o}</li>)}</ul>
      : <div className="fine">Nothing open.</div>}

    <h2 className="rsec">Narrative</h2>
    <div className="nar">{r.narrative.split('\n\n').filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}</div>

    <footer className="rfoot">{r.disclosures.join(' · ')}</footer>
  </div></div>
}
