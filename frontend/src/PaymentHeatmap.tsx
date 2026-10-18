import './pages.css'
import { getHeatmap } from './api'
import { useLoad } from './useLoad'
import { HEAT_LABEL, HEAT_LEGEND, cellTitle, chunk, heatClass, heatSummary, monthLabel } from './heatmapUtils'
import { money, withCompany } from './pageUtils'

/** GitHub-contribution-style grid: one row per customer, one square per due month (last 12 months). */
export function PaymentHeatmap({ company, limit, compact = false, columns = 2 }: { company: string; limit?: number; compact?: boolean; columns?: number }) {
  const res = useLoad(() => getHeatmap(company), company)
  const d = res.data
  const rows = d ? (limit ? d.customers.slice(0, limit) : d.customers) : []
  const sum = heatSummary(d?.customers || [])
  const pl = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

  return <section className={`card pg-sec hm ${compact ? 'compact' : ''}`} data-testid="payment-heatmap">
    <div className="head"><b>How customers pay</b>
      <span className="fine">each square is a month of invoices by due date{limit && d && d.customers.length > limit ? ` · top ${limit} by open balance` : ''}</span>
    </div>
    {res.error && !d ? <div className="fine" role="alert" style={{ color: 'var(--red)' }}>Payment heatmap unavailable: {res.error} <button className="linkish" onClick={res.reload}>Retry</button></div>
      : !d ? <div className="thinking" style={{ height: 60 }}><i/><i/><i/> loading</div>
      : rows.length === 0 ? <div className="fine">No invoices due in the last 12 months.</div>
      : <>
        <div className="hm-sum" data-testid="heatmap-summary">
          <span><i className="hm-c hm-paid-on-time" />{pl(sum.onTime, 'customer', 'customers')} paid everything on time</span>
          {sum.late > 0 && <span><i className="hm-c hm-paid-late" />{sum.late} paid late but nothing overdue</span>}
          <span><i className="hm-c hm-overdue" />{pl(sum.overdue, 'customer has', 'customers have')} overdue invoices</span>
          {sum.writtenOff > 0 && <span><i className="hm-c hm-written-off" />{sum.writtenOff} with write-offs</span>}
        </div>
        <div className="hm-blocks">{chunk(rows, columns).map((block, bi) =>
          <div className="hm-grid" role="table" aria-label={`Payment heatmap by customer and month${columns > 1 ? `, part ${bi + 1}` : ''}`} key={bi}>
            <div className="hm-row hm-months" role="row">
              <span className="hm-name" role="columnheader" />
              <span className="hm-cells">{d.months.map((m, i) => <span key={m} className="hm-m" role="columnheader" title={monthLabel(m, true)}>{i % 2 === 0 ? monthLabel(m) : ''}</span>)}</span>
              <span className="hm-bal" role="columnheader">Open</span>
            </div>
            {block.map(c => <div className="hm-row" role="row" key={c.id}>
              <a className="strong hm-name" role="rowheader" href={withCompany(`/customers/${encodeURIComponent(c.id)}`, company)} title={c.display_name}>{c.display_name}</a>
              <span className="hm-cells">{c.cells.map(x => <i key={x.month} role="cell" className={heatClass(x.status)} title={cellTitle(x)} aria-label={cellTitle(x)} />)}</span>
              <span className="hm-bal">{money(c.open_balance)}</span>
            </div>)}
          </div>)}
        </div>
        <div className="legend hm-legend">{HEAT_LEGEND.map(s => <span key={s}><i className={heatClass(s)} />{HEAT_LABEL[s]}</span>)}</div>
        {compact && <a className="fine hm-more" href={withCompany('/customers', company)}>All customers →</a>}
      </>}
  </section>
}
