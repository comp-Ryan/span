import { describe, expect, it } from 'vitest'
import { coverageSeries, type HistoryPoint } from './forecastTrend'

const point = (over: Partial<HistoryPoint>): HistoryPoint => ({ forecast_id: '1', run_id: 'r', computed_at: '2026-10-17T20:00:00Z', target: '2026-10-20', cash_at_target: 12890.06, need: 13275, gap: 384.94, pessimistic_gap: 2752.92, ...over })

describe('forecast over time', () => {
  it('turns saved forecasts into a coverage series, oldest first, with the latest summary', () => {
    const series = coverageSeries([
      point({ forecast_id: '1', computed_at: '2026-10-17T20:00:00Z', gap: 384.94 }),
      point({ forecast_id: '2', computed_at: '2026-10-17T20:05:00Z', gap: 668.96, excluded_customer_id: 'cust-37' }),
      point({ forecast_id: '3', computed_at: '2026-10-17T20:09:00Z', gap: -120.5 }),
    ])
    expect(series.points.map(p => p.coverage)).toEqual([-384.94, -668.96, 120.5])
    expect(series.points[1].label).toContain('cust-37')
    expect(series.latest).toEqual({ coverage: 120.5, target: '2026-10-20', computed_at: '2026-10-17T20:09:00Z' })
    expect(series.low).toBe(-668.96)
    expect(series.high).toBe(120.5)
  })
  it('sorts by computed_at and skips points without numbers', () => {
    const series = coverageSeries([
      point({ forecast_id: 'b', computed_at: '2026-10-17T21:00:00Z', gap: 10 }),
      point({ forecast_id: 'a', computed_at: '2026-10-17T20:00:00Z', gap: 5 }),
      point({ forecast_id: 'c', computed_at: '2026-10-17T22:00:00Z', gap: Number.NaN }),
    ])
    expect(series.points.map(p => p.forecast_id)).toEqual(['a', 'b'])
    expect(coverageSeries([]).points).toEqual([])
    expect(coverageSeries([]).latest).toBeNull()
  })
})
