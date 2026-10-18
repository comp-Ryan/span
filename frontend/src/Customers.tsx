import { useMemo, useState } from 'react'
import { getCustomer, getCustomers, startRun } from './api'
import { Empty, ErrorCard, Loading, PageHead, Shell } from './Shell'
import { ICONS } from './icons'
import { useLoad } from './useLoad'
import { PaymentHeatmap } from './PaymentHeatmap'
import type { CustomerActivity, CustomerHistoryItem } from './types'
import {
  ago, cents, chatUrl, currentCompany, defaultDir, filterCustomers, fmtDate, fmtDateTime, historyTone, money,
  reliabilityLabel, sortCustomers, withCompany, type CustomerSortKey, type SortDir,
} from './pageUtils'

const COLS: [CustomerSortKey, string, boolean][] = [
  ['display_name', 'Customer', false], ['open_balance', 'Open', true], ['overdue_balance', 'Overdue', true],
  ['open_invoices', 'Open invoices', true], ['avg_days_late', 'Avg days late', true], ['reliability', 'Reliability', false],
]

export function CustomersList() {
  const company = currentCompany()
  const res = useLoad(() => getCustomers(company), company)
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<{ key: CustomerSortKey; dir: SortDir }>({ key: 'open_balance', dir: 'desc' })
  const rows = useMemo(() => sortCustomers(filterCustomers(res.data || [], q), sort.key, sort.dir), [res.data, q, sort])
  const all = res.data || []
  const owed = all.reduce((a, c) => a + c.open_balance, 0)
  const overdue = all.reduce((a, c) => a + c.overdue_balance, 0)
  const clickSort = (key: CustomerSortKey) => setSort(s => s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: defaultDir(key) })
  const open = (id: string) => { location.assign(withCompany(`/customers/${encodeURIComponent(id)}`, company)) }

  return <Shell active="customers" company={company} testId="customers">
    <PageHead title="Customers"
      sub={res.data ? <span>{all.length} customers · {money(owed)} owed · {money(overdue)} overdue</span> : <span>Who owes you, and how reliably they pay.</span>}
      right={<label className="pg-search"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg><input placeholder="Search customers" aria-label="Search customers" value={q} onChange={e => setQ(e.target.value)} /></label>} />
    <PaymentHeatmap company={company} />
    {res.error && <ErrorCard what="Customers" error={res.error} onRetry={res.reload} />}
    {!(res.error && !res.data) && <section className="card pg-sec" data-testid="customer-table">
      {!res.data && res.loading ? <Loading /> : res.data && all.length === 0 ? <Empty title="No customers in these books" /> : res.data && rows.length === 0 ? <Empty title={`No customers match “${q}”`}><button className="linkish" onClick={() => setQ('')}>Clear search</button></Empty> : res.data && <table className="tbl hover">
        <thead><tr>{COLS.map(([key, label, num]) => <th key={key} className={`${num ? 'num' : ''} sortable`} aria-sort={sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
          <button onClick={() => clickSort(key)}>{label}<span className="arr">{sort.key === key ? (sort.dir === 'asc' ? '▲' : '▼') : ''}</span></button>
        </th>)}</tr></thead>
        <tbody>{rows.map(c => <tr key={c.id} tabIndex={0} onClick={() => open(c.id)} onKeyDown={e => { if (e.key === 'Enter') open(c.id) }}>
          <td><a className="strong" href={withCompany(`/customers/${encodeURIComponent(c.id)}`, company)} onClick={e => e.stopPropagation()}>{c.display_name}</a></td>
          <td className="num">{money(c.open_balance)}</td>
          <td className={`num ${c.overdue_balance > 0 ? 'warn' : 'muted'}`}>{money(c.overdue_balance)}</td>
          <td className="num">{c.open_invoices}</td>
          <td className="num">{c.avg_days_late == null ? '—' : Math.round(c.avg_days_late)}</td>
          <td><span className="rel"><i className={`rdot ${c.reliability || 'none'}`} />{reliabilityLabel(c.reliability)}</span></td>
        </tr>)}</tbody>
      </table>}
    </section>}
  </Shell>
}

function HistoryStrip({ history }: { history: CustomerHistoryItem[] }) {
  const paid = history.filter(h => h.status === 'paid')
  const avg = paid.length ? paid.reduce((a, h) => a + (h.days_late || 0), 0) / paid.length : 0
  const lost = history.filter(h => h.status === 'written_off').length
  if (!history.length) return <Empty title="No invoice history yet" />
  return <div className="hstrip">
    <div className="bars">{history.slice(-48).map((h, i) => <i key={i} className={historyTone(h)} style={{ height: 12 + Math.min(28, Math.max(0, (h.days_late ?? 0) / 2)) }} title={`${h.invoice_id} · due ${fmtDate(h.due_date)} · ${h.status === 'open' ? 'still open' : `${h.days_late ?? '—'} days late`} · ${money(h.amount)}`} />)}</div>
    <div className="kv"><span style={{ color: 'var(--muted)' }}>{paid.length} invoice{paid.length === 1 ? '' : 's'} paid, usually {Math.round(avg)} days late</span><b>{lost ? `${lost} written off` : 'never written off'}</b></div>
    <div className="legend"><span><i style={{ background: 'var(--green)' }} />on time-ish</span><span><i style={{ background: 'var(--amber)' }} />late</span><span><i style={{ background: 'var(--red)' }} />very late / lost</span><span><i style={{ background: 'var(--line)' }} />still open</span></div>
  </div>
}

const ACT_ICON: Record<CustomerActivity['kind'], [React.ReactNode, string]> = {
  reminder: [ICONS.bell, 'blue'], reply: [ICONS.reply, 'grey'], negotiation: [ICONS.handshake, 'amber'], payment: [ICONS.check, 'green'],
}

export function CustomerDetailPage({ id }: { id: string }) {
  const company = currentCompany()
  const res = useLoad(() => getCustomer(id, company), `${company}/${id}`)
  const [asking, setAsking] = useState(false)
  const [askErr, setAskErr] = useState('')
  const d = res.data
  const c = d?.customer
  const ask = async () => {
    if (!c || asking) return
    setAsking(true); setAskErr('')
    try { const { run_id } = await startRun(company, `How is ${c.display_name} doing, and should I chase them?`); location.assign(chatUrl(run_id, company)) }
    catch (e) { setAskErr(e instanceof Error ? e.message : String(e)); setAsking(false) }
  }
  const notFound = res.error && /not found|404/i.test(res.error)

  return <Shell active="customers" company={company} testId="customer-detail">
    <a className="back" href={withCompany('/customers', company)}>← All customers</a>
    {res.error && (notFound ? <section className="card pg-sec"><Empty title="Customer not found">This customer isn’t in these books. <a href={withCompany('/customers', company)}>Back to customers</a></Empty></section> : <ErrorCard what="This customer" error={res.error} onRetry={res.reload} />)}
    {!d && res.loading && <Loading />}
    {d && c && <>
      <PageHead title={c.display_name}
        sub={<><span className="rel"><i className={`rdot ${c.reliability || 'none'}`} />{reliabilityLabel(c.reliability)}</span><span className="sep" /><span>{c.payment_terms || 'No terms on file'}</span><span className="sep" /><span>{c.paid_invoices} paid invoice{c.paid_invoices === 1 ? '' : 's'}</span></>}
        right={<div className="ask-c"><button className="btn primary" onClick={ask} disabled={asking}>{ICONS.chat}{asking ? 'Starting…' : 'Ask Span about this customer'}</button>{askErr && <span className="fine" role="alert" style={{ color: 'var(--red)' }}>{askErr}</span>}</div>} />

      <div className="stats cust-stats">
        <div className="stat"><span className="sl">Open balance</span><span className="sv">{money(c.open_balance)}</span></div>
        <div className="stat"><span className="sl">Overdue</span><span className="sv" style={{ color: c.overdue_balance > 0 ? 'var(--red)' : undefined }}>{money(c.overdue_balance)}</span></div>
        <div className="stat"><span className="sl">Open invoices</span><span className="sv">{c.open_invoices}</span></div>
        <div className="stat"><span className="sl">Avg days late</span><span className="sv">{c.avg_days_late == null ? '—' : Math.round(c.avg_days_late)}</span></div>
        <div className="stat"><span className="sl">Written off</span><span className="sv">{money(c.written_off)}</span></div>
      </div>

      <section className="card pg-sec" data-testid="history-strip">
        <div className="head"><b>Payment history</b><span className="fine">each bar is an invoice, taller = paid later</span></div>
        <HistoryStrip history={d.history} />
      </section>

      <div className="cust-grid">
        <section className="card pg-sec" data-testid="open-invoices">
          <div className="head"><b>Open invoices</b><span className="fine">likelihood of payment by payday, {fmtDate(d.target_date)}</span></div>
          {d.invoices.length === 0 ? <Empty title="Nothing open">This customer is all paid up.</Empty> : <table className="tbl">
            <thead><tr><th>Invoice</th><th className="num">Open</th><th>Due</th><th className="num">Past due</th><th>Paid by payday</th></tr></thead>
            <tbody>{d.invoices.map(inv => <tr key={inv.invoice_id}>
              <td className="strong">{inv.doc_number || inv.invoice_id}</td>
              <td className="num">{cents(inv.open_balance)}</td>
              <td>{fmtDate(inv.due_date)}</td>
              <td className={`num ${inv.days_past_due > 0 ? 'warn' : 'muted'}`}>{inv.days_past_due > 0 ? `${inv.days_past_due} d` : 'not yet'}</td>
              <td><div className="prob"><div className="bar"><i style={{ width: `${Math.round(inv.p_paid_by_target * 100)}%`, background: `var(--${inv.band})` }} /></div><span className={`pc ${inv.band}`}>{Math.round(inv.p_paid_by_target * 100)}%</span></div>
                {inv.p_never >= 0.15 && <div className="fine">{Math.round(inv.p_never * 100)}% risk it’s never paid</div>}</td>
            </tr>)}</tbody>
          </table>}
        </section>

        <section className="card pg-sec" data-testid="activity">
          <div className="head"><b>Activity</b><span className="fine">reminders, replies, negotiations and payments</span></div>
          {d.activity.length === 0 ? <Empty title="No activity yet">Span hasn’t contacted this customer. Ask about them to decide whether to chase.</Empty> : <ol className="timeline">
            {d.activity.map((a, i) => { const [icon, cls] = ACT_ICON[a.kind] || [ICONS.clock, 'grey']; return <li key={i}>
              <span className={`ic ${cls}`}>{icon}</span>
              <div className="tl-body">
                <div className="tl-top"><b>{a.title}</b><span className="fine" title={fmtDateTime(a.at)}>{ago(a.at)}</span></div>
                {a.detail && <div className="tl-detail">{a.detail}</div>}
                {a.run_id && <a className="fine" href={chatUrl(a.run_id, company)}>Open the chat →</a>}
              </div>
            </li> })}
          </ol>}
        </section>
      </div>
    </>}
  </Shell>
}
