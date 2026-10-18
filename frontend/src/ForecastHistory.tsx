import { useEffect, useState } from 'react'
import { cents } from './pageUtils'
type Revision = { forecast_id: string; computed_at: string; target: string; forecast: { cash_at_target: number; need: number; pessimistic: { cash_at_target: number }; excluded_customer_id?: string; assumed_customer_id?: string } }
export default function ForecastHistory({ company, runId, revision }: { company: string; runId: string; revision: string }) {
  const [rows, setRows] = useState<Revision[]>([])
  const [error, setError] = useState(false)
  useEffect(() => {
    const abort = new AbortController()
    fetch(`/api/forecasts?${new URLSearchParams({ company, run_id: runId, limit: '20' })}`, { signal: abort.signal }).then(async r => {
      if (!r.ok) throw new Error('Forecast history unavailable')
      const body = await r.json(); setRows(body.forecasts); setError(false)
    }).catch(e => { if (e.name !== 'AbortError') setError(true) })
    return () => abort.abort()
  }, [company, runId, revision])
  if (error) return <div className="card fine" role="alert">Forecast history unavailable</div>
  if (!rows.length) return null
  const value = (r: Revision, pessimistic = false) => (pessimistic ? r.forecast.pessimistic.cash_at_target : r.forecast.cash_at_target) - r.forecast.need
  const values = rows.flatMap(r => [value(r), value(r, true)]), lo = Math.min(0, ...values), hi = Math.max(1, ...values)
  const x = (i: number) => 12 + i * 376 / Math.max(1, rows.length - 1), y = (n: number) => 110 - 95 * (n - lo) / (hi - lo)
  const line = (p: boolean) => rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(value(r, p))}`).join(' ')
  return <div className="card forecast-history" data-testid="forecast-history"><b>Forecast history</b>
    <div className="fine">Payroll coverage estimate · saved revisions</div>
    <svg viewBox="0 0 400 130" role="img" aria-label="Expected and pessimistic payroll coverage across saved forecasts">
      <path d={`M0 ${y(0)}H400`} stroke="#aaa" strokeDasharray="3 4" />
      <path d={line(false)} fill="none" stroke="#2CA01C" strokeWidth="2" /><path d={line(true)} fill="none" stroke="#E08A00" strokeWidth="2" />
      {rows.map((r, i) => <g key={r.forecast_id}><circle cx={x(i)} cy={y(value(r))} r="4" fill="#2CA01C"><title>{r.computed_at} · target {r.target}: {cents(value(r))}</title></circle><circle cx={x(i)} cy={y(value(r, true))} r="3" fill="#E08A00" /></g>)}
    </svg><div className="kv"><span>Expected {cents(value(rows.at(-1)!))}</span><span>Pessimistic {cents(value(rows.at(-1)!, true))}</span></div>
    <div className="fine">{rows.length} revisions · TimescaleDB / Tiger Data compatible. Negative = short; each point retains its own target and assumptions.</div>
  </div>
}
