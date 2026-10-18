import type { HeatmapCell, HeatmapCustomer, HeatmapStatus } from './types'

/** Worst-first, matching the backend's per-month status order. */
export const HEAT_OUTCOMES = ['written_off', 'overdue', 'very_late', 'paid_late', 'unpaid', 'paid_on_time'] as const

export const HEAT_LABEL: Record<HeatmapStatus, string> = {
  paid_on_time: 'Paid on time', paid_late: 'Paid late', very_late: 'Very late (30+ days)',
  unpaid: 'Not yet due', overdue: 'Overdue', written_off: 'Written off', none: 'No invoices',
}

/** Legend order, mildest to worst, then empty. */
export const HEAT_LEGEND: HeatmapStatus[] = ['paid_on_time', 'paid_late', 'very_late', 'unpaid', 'overdue', 'written_off', 'none']

const KNOWN = new Set<string>([...HEAT_OUTCOMES, 'none'])

/** CSS class for a cell; unknown statuses fall back to empty. */
export const heatClass = (status: string | null | undefined): string =>
  `hm-c hm-${status && KNOWN.has(status) ? status.replace(/_/g, '-') : 'none'}`

/** "2026-03" -> "Mar" (short) or "March 2026" (long). */
export function monthLabel(month: string, long = false): string {
  const [y, m] = month.split('-').map(Number)
  if (!y || !m) return month
  return new Date(y, m - 1, 1).toLocaleDateString('en-US', long ? { month: 'long', year: 'numeric' } : { month: 'short' })
}

const usd = (v: number) => '$' + Math.round(v).toLocaleString('en-US')

/** Native tooltip text: month, invoice count, amount, and non-zero outcome counts. */
export function cellTitle(cell: HeatmapCell): string {
  const head = monthLabel(cell.month, true)
  if (!cell.invoices) return `${head}: no invoices due`
  const counts = HEAT_LEGEND.filter(s => s !== 'none' && cell[s as Exclude<HeatmapStatus, 'none'>] > 0)
    .map(s => `${cell[s as Exclude<HeatmapStatus, 'none'>]} ${HEAT_LABEL[s].toLowerCase()}`)
  return `${head}: ${cell.invoices} invoice${cell.invoices === 1 ? '' : 's'} due · ${usd(cell.amount)}\n${counts.join(' · ')}`
}

/** Split rows into `n` column-major blocks of near-equal length (first blocks take the extra rows). */
export function chunk<T>(rows: T[], n: number): T[][] {
  const k = Math.max(1, Math.min(Math.floor(n) || 1, rows.length || 1))
  const size = Math.ceil(rows.length / k)
  return Array.from({ length: k }, (_, i) => rows.slice(i * size, (i + 1) * size)).filter((b, i) => b.length || i === 0)
}

export interface HeatSummary { total: number; onTime: number; late: number; overdue: number; writtenOff: number }

/**
 * onTime: every invoice in the window paid on time or not yet due.
 * overdue: at least one month with an unpaid, past-due invoice.
 * late: neither of the above — paid late / very late but nothing currently overdue.
 */
export function heatSummary(rows: HeatmapCustomer[]): HeatSummary {
  let onTime = 0, late = 0, overdue = 0, writtenOff = 0
  for (const r of rows) {
    const seen = new Set(r.cells.filter(c => c.invoices > 0).map(c => c.status))
    if (seen.has('written_off')) writtenOff++
    if (seen.has('overdue')) overdue++
    else if ([...seen].every(s => s === 'paid_on_time' || s === 'unpaid')) onTime++
    else late++
  }
  return { total: rows.length, onTime, late, overdue, writtenOff }
}
