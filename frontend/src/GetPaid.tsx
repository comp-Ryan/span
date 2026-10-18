import { getHealth, getPayments } from './api'
import { Empty, ErrorCard, Loading, PageHead, Shell } from './Shell'
import { ICONS } from './icons'
import { useLoad } from './useLoad'
import { ago, cents, chatUrl, currentCompany, fmtDateTime, money, railLabel, railReadiness, shortRef, withCompany } from './pageUtils'

const payPageUrl = (token: string) => `/api/pay/${encodeURIComponent(token)}/page`

function Tile({ icon, cls, label, value, sub, loading }: { icon: React.ReactNode; cls: string; label: string; value?: string; sub?: string; loading?: boolean }) {
  return <div className="card tile">
    <div className="tl"><span className={`ic ${cls}`}>{icon}</span>{label}</div>
    {loading ? <div className="thinking" style={{ marginTop: 10 }}><i/><i/><i/></div> : <>
      <div className="tv">{value ?? '—'}</div>
      <div className="fine">{sub || '\u00a0'}</div>
    </>}
  </div>
}

export default function GetPaid() {
  const company = currentCompany()
  const pay = useLoad(() => getPayments(company), company)
  const health = useLoad(() => getHealth(), 'health')
  const d = pay.data
  const rails = railReadiness(health.data)
  const loading = !d && pay.loading

  return <Shell active="get-paid" company={company} testId="get-paid">
    <PageHead title="Get paid" sub={<span>Pay links Span sent to customers, and the money that came back.</span>}
      right={<div className="rails" data-testid="rail-readiness">
        {health.error ? <span className="fine">Rail status unavailable</span> : !health.data ? <span className="fine">Checking payment rails…</span> : <>
          <span className={`rail-chip ${rails.visa.ok ? 'ok' : ''}`}><i />{rails.visa.label}</span>
          <span className={`rail-chip ${rails.solana.ok ? 'ok' : ''}`}><i />{rails.solana.label}</span>
        </>}
      </div>} />

    {pay.error && <ErrorCard what="Payments" error={pay.error} onRetry={pay.reload} />}

    {!(pay.error && !d) && <>
    <div className="tiles three">
      <Tile icon={ICONS.check} cls="green" label="Collected" loading={loading} value={d ? money(d.totals.collected) : undefined} sub={d ? `${d.payments.length} payment${d.payments.length === 1 ? '' : 's'} received` : undefined} />
      <Tile icon={ICONS.clock} cls="amber" label="Outstanding on links" loading={loading} value={d ? money(d.totals.outstanding) : undefined} sub={d ? `across ${d.totals.unpaid} unpaid link${d.totals.unpaid === 1 ? '' : 's'}` : undefined} />
      <Tile icon={ICONS.link} cls="blue" label="Open pay links" loading={loading} value={d ? String(d.totals.unpaid) : undefined} sub={d ? `${d.totals.links} sent in total` : undefined} />
    </div>

    <section className="card pg-sec" data-testid="pay-links">
      <div className="head"><b>Pay links</b><span className="fine">{d ? `${d.pay_links.length} link${d.pay_links.length === 1 ? '' : 's'}` : ''}</span></div>
      {loading ? <Loading /> : d && d.pay_links.length === 0 ? <Empty title="No pay links yet">When you approve a reminder in a chat, Span texts the customer a pay link. They’ll show up here. <a href={withCompany('/', company)}>Ask who to chase →</a></Empty> : d && <table className="tbl">
        <thead><tr><th>Customer</th><th>Invoice</th><th className="num">Amount</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>{d.pay_links.map(l => <tr key={l.pay_token}>
          <td><a className="strong" href={withCompany(`/customers/${encodeURIComponent(l.customer_id)}`, company)}>{l.customer_name}</a></td>
          <td>{l.doc_number || l.invoice_id}</td>
          <td className="num">{cents(l.amount)}</td>
          <td><span className={`pill-v ${l.status === 'paid' ? 'green' : 'amber'}`}>{l.status === 'paid' ? 'Paid' : l.status === 'unpaid' ? 'Unpaid' : l.status}</span></td>
          <td className="fine" title={fmtDateTime(l.created_at)}>{ago(l.created_at)}{l.run_id && <> · <a href={chatUrl(l.run_id, company)}>chat</a></>}</td>
          <td className="act"><a className="btn sm" href={payPageUrl(l.pay_token)} target="_blank" rel="noreferrer">Open pay page</a></td>
        </tr>)}</tbody>
      </table>}
    </section>

    <section className="card pg-sec" data-testid="payments">
      <div className="head"><b>Payments received</b><span className="fine">Test rails only: cards go through the Visa sandbox (or a simulator), USDC settles on Solana devnet. No real money moves.</span></div>
      {loading ? <Loading /> : d && d.payments.length === 0 ? <Empty title="No payments yet">Once a customer pays through a link, the payment and its receipt reference land here.</Empty> : d && <table className="tbl">
        <thead><tr><th>Customer</th><th>Invoice</th><th className="num">Amount</th><th>Rail</th><th>Reference</th><th>Paid</th><th></th></tr></thead>
        <tbody>{d.payments.map(p => <tr key={p.payment_id}>
          <td className="strong">{p.customer_name}</td>
          <td>{p.invoice_id}</td>
          <td className="num">{cents(p.amount)}</td>
          <td><span className={`pill-v ${railLabel(p.rail).startsWith('Solana') ? 'violet' : 'blue'}`}>{railLabel(p.rail)}</span></td>
          <td className="mono" title={p.reference || undefined}>{shortRef(p.reference)}</td>
          <td className="fine" title={fmtDateTime(p.paid_at)}>{ago(p.paid_at)}</td>
          <td className="act">{p.run_id ? <a className="btn sm ghost-l" href={chatUrl(p.run_id, company)}>Open chat</a> : <span className="fine">—</span>}</td>
        </tr>)}</tbody>
      </table>}
    </section>
    </>}
  </Shell>
}
