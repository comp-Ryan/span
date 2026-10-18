import { describe, expect, it } from 'vitest'
import { HEAT_LEGEND, cellTitle, chunk, heatClass, heatSummary, monthLabel } from './heatmapUtils'
import type { HeatmapCell, HeatmapCustomer, HeatmapStatus } from './types'

const cell = (month: string, status: HeatmapStatus, counts: Partial<HeatmapCell> = {}): HeatmapCell => {
  const base = { paid_on_time: 0, paid_late: 0, very_late: 0, unpaid: 0, overdue: 0, written_off: 0, ...counts }
  const invoices = base.paid_on_time + base.paid_late + base.very_late + base.unpaid + base.overdue + base.written_off
  return { month, status, invoices, amount: counts.amount ?? invoices * 100, ...base }
}
const cust = (id: string, statuses: HeatmapStatus[]): HeatmapCustomer => ({
  id, display_name: id, open_balance: 0,
  cells: statuses.map((s, i) => s === 'none' ? cell(`2026-${String(i + 1).padStart(2, '0')}`, 'none') : cell(`2026-${String(i + 1).padStart(2, '0')}`, s, { [s]: 1 })),
})

describe('heatClass', () => {
  it('maps every status to a kebab-case class', () => {
    expect(heatClass('paid_on_time')).toBe('hm-c hm-paid-on-time')
    expect(heatClass('written_off')).toBe('hm-c hm-written-off')
    expect(heatClass('overdue')).toBe('hm-c hm-overdue')
    expect(heatClass('none')).toBe('hm-c hm-none')
    expect(new Set(HEAT_LEGEND.map(heatClass)).size).toBe(7)
  })
  it('falls back to empty for unknown or missing statuses', () => {
    expect(heatClass('bogus')).toBe('hm-c hm-none')
    expect(heatClass(undefined)).toBe('hm-c hm-none')
    expect(heatClass(null)).toBe('hm-c hm-none')
  })
})

describe('monthLabel / cellTitle', () => {
  it('formats months', () => {
    expect(monthLabel('2025-11')).toBe('Nov')
    expect(monthLabel('2026-03', true)).toBe('March 2026')
    expect(monthLabel('garbage')).toBe('garbage')
  })
  it('lists month, count, amount and non-zero outcomes', () => {
    const t = cellTitle(cell('2026-02', 'overdue', { paid_late: 2, overdue: 1, amount: 1234.5 }))
    expect(t).toContain('February 2026: 3 invoices due · $1,235')
    expect(t).toContain('2 paid late')
    expect(t).toContain('1 overdue')
    expect(t).not.toContain('written off')
    expect(cellTitle(cell('2026-02', 'none'))).toBe('February 2026: no invoices due')
  })
})

describe('heatSummary', () => {
  it('buckets customers into on time / late / overdue', () => {
    const s = heatSummary([
      cust('a', ['paid_on_time', 'none', 'unpaid']),
      cust('b', ['paid_on_time', 'paid_late']),
      cust('c', ['very_late', 'overdue']),
      cust('d', ['written_off', 'paid_on_time']),
      cust('e', ['none', 'overdue', 'written_off']),
    ])
    expect(s).toEqual({ total: 5, onTime: 1, late: 2, overdue: 2, writtenOff: 2 })
  })
  it('handles an empty list', () => {
    expect(heatSummary([])).toEqual({ total: 0, onTime: 0, late: 0, overdue: 0, writtenOff: 0 })
  })
})

describe('chunk', () => {
  it('splits into near-equal column-major blocks', () => {
    expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2, 3], [4, 5]])
    expect(chunk([1, 2], 3)).toEqual([[1], [2]])
    expect(chunk([], 2)).toEqual([[]])
    expect(chunk([1, 2, 3], 0)).toEqual([[1, 2, 3]])
  })
})
