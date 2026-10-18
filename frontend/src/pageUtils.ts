import { money as moneyPos } from './events'
import type { CustomerRow } from './types'

export const DEFAULT_COMPANY = 'company-020'

/** Company from `?company=`, falling back to the demo company. */
export const currentCompany = (search = typeof location !== 'undefined' ? location.search : '') =>
  new URLSearchParams(search).get('company') || DEFAULT_COMPANY

/** Append `company=` to an in-app path unless it's the default company. */
export function withCompany(path: string, company: string): string {
  if (company === DEFAULT_COMPANY) return path
  return `${path}${path.includes('?') ? '&' : '?'}company=${encodeURIComponent(company)}`
}

/** Link to a chat on the canvas, replaying it live. */
export const chatUrl = (runId: string, company: string) => withCompany(`/?run=${encodeURIComponent(runId)}&live`, company)

/** Same as Home's `money`: proper minus sign for negatives. */
export const money = (v?: number | null) => v != null && v < 0 ? `−${moneyPos(-v)}` : moneyPos(v ?? undefined)

/** Exact dollars and cents, for payment rows. */
export const cents = (v?: number | null) => v == null ? '—' : (v < 0 ? '−' : '') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function ago(s: string | null | undefined, now = Date.now()): string {
  if (!s) return '—'
  const t = new Date(s).getTime(); const m = Math.round((now - t) / 60000)
  if (!isFinite(m)) return '—'
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60); if (h < 24) return `${h} h ago`
  return new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
export const fmtDate = (s?: string | null) => s ? new Date(s.length === 10 ? s + 'T00:00:00' : s).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'
export const fmtDateTime = (s?: string | null) => s ? new Date(s).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'

/** Honest rail labels for payment rows. */
export function railLabel(rail: string | null | undefined): string {
  const r = (rail || '').toLowerCase()
  if (r.includes('sol') || r.includes('usdc')) return 'Solana devnet'
  if (r.includes('visa') || r.includes('card')) return 'Visa sandbox'
  return rail || 'Unknown'
}

/** One-line readiness from /health's `visa` / `solana` fields. */
export function railReadiness(h: { visa?: unknown; solana?: unknown } | null | undefined) {
  const visa = String(h?.visa ?? '')
  const sol = String(h?.solana ?? '')
  return {
    visa: visa === 'sandbox' || visa === 'live' || visa === 'configured' || visa === 'true' ? { ok: true, label: 'Visa sandbox ready' } : { ok: false, label: visa ? `Card payments ${visa}` : 'Card payments unknown' },
    solana: sol && sol !== 'unconfigured' && sol !== 'false' ? { ok: true, label: `Solana ${sol === 'true' ? 'devnet' : sol} ready` } : { ok: false, label: sol ? `Solana devnet ${sol}` : 'Solana unknown' },
  }
}

/** Shorten long references/signatures for table cells. */
export const shortRef = (ref?: string | null, keep = 8) => !ref ? '—' : ref.length <= keep * 2 + 1 ? ref : `${ref.slice(0, keep)}…${ref.slice(-keep)}`

export type CustomerSortKey = 'display_name' | 'open_balance' | 'overdue_balance' | 'open_invoices' | 'avg_days_late' | 'reliability'
export type SortDir = 'asc' | 'desc'
const RELIABILITY_RANK: Record<string, number> = { green: 0, amber: 1, red: 2 }

export function filterCustomers(rows: CustomerRow[], query: string): CustomerRow[] {
  const q = query.trim().toLowerCase()
  if (!q) return rows
  return rows.filter(r => r.display_name.toLowerCase().includes(q) || r.id.toLowerCase().includes(q))
}

/** Stable sort; nulls (no reliability / no history) always go last. */
export function sortCustomers(rows: CustomerRow[], key: CustomerSortKey, dir: SortDir): CustomerRow[] {
  const val = (r: CustomerRow): string | number | null => {
    if (key === 'display_name') return r.display_name.toLowerCase()
    if (key === 'reliability') return r.reliability == null ? null : RELIABILITY_RANK[r.reliability] ?? null
    return r[key] ?? null
  }
  const sign = dir === 'asc' ? 1 : -1
  return rows.map((r, i) => ({ r, i, v: val(r) })).sort((a, b) => {
    if (a.v == null && b.v == null) return a.i - b.i
    if (a.v == null) return 1
    if (b.v == null) return -1
    const c = typeof a.v === 'string' ? a.v.localeCompare(b.v as string) : (a.v as number) - (b.v as number)
    return c !== 0 ? c * sign : a.i - b.i
  }).map(x => x.r)
}

/** Default direction when a column header is first clicked: text ascending, numbers descending. */
export const defaultDir = (key: CustomerSortKey): SortDir => key === 'display_name' || key === 'reliability' ? 'asc' : 'desc'

export const reliabilityLabel = (r: CustomerRow['reliability']) => r === 'green' ? 'Reliable' : r === 'amber' ? 'Pays late' : r === 'red' ? 'At risk' : 'No open invoices'

/** Colour for a historical invoice in the payment-history strip. */
export function historyTone(h: { status: string; days_late: number | null }): 'green' | 'amber' | 'red' | 'grey' {
  if (h.status === 'written_off') return 'red'
  if (h.status === 'open' || h.status === 'partial') return h.days_late == null ? 'grey' : h.days_late > 30 ? 'red' : 'amber'
  const d = h.days_late ?? 0
  return d <= 7 ? 'green' : d <= 30 ? 'amber' : 'red'
}

/** Strip light markdown (bold, code, headings) from model answers shown in one-line pills. */
export const plainText = (s?: string | null) => (s || '').replace(/\*\*|__|`/g, '').replace(/^#+\s*/gm, '').replace(/\s+/g, ' ').trim()
