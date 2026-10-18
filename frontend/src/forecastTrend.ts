/** Saved payroll forecasts over time (GET /cash/history): coverage = cash before payroll minus payroll need. */
export type HistoryPoint = {
  forecast_id: string; run_id: string; node_id?: string; computed_at: string; target: string
  cash_at_target: number; need: number; gap: number; pessimistic_gap?: number | null
  excluded_customer_id?: string | null; assumed_customer_id?: string | null
}
export type TrendPoint = { forecast_id: string; computed_at: string; target: string; coverage: number; label: string }

export function coverageSeries(points: HistoryPoint[]) {
  const sorted = points.filter(p => Number.isFinite(p.gap)).sort((a, b) => Date.parse(a.computed_at) - Date.parse(b.computed_at))
  const out: TrendPoint[] = sorted.map(p => ({
    forecast_id: p.forecast_id, computed_at: p.computed_at, target: p.target, coverage: p.gap === 0 ? 0 : -p.gap,
    label: `payday ${p.target}${p.excluded_customer_id ? ` · without ${p.excluded_customer_id}` : ''}${p.assumed_customer_id ? ` · assuming ${p.assumed_customer_id} pays` : ''}`,
  }))
  const values = out.map(p => p.coverage)
  const last = out.at(-1)
  return {
    points: out,
    latest: last ? { coverage: last.coverage, target: last.target, computed_at: last.computed_at } : null,
    low: values.length ? Math.min(0, ...values) : 0,
    high: values.length ? Math.max(0, ...values) : 0,
  }
}
