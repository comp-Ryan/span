import { describe, expect, it } from 'vitest'
import { ago, cents, chatUrl, currentCompany, defaultDir, filterCustomers, historyTone, money, railLabel, railReadiness, plainText, shortRef, sortCustomers, withCompany } from './pageUtils'
import type { CustomerRow } from './types'

const row = (id: string, name: string, open: number, rel: CustomerRow['reliability'], late: number | null = 10): CustomerRow =>
  ({ id, display_name: name, open_balance: open, overdue_balance: open / 2, open_invoices: 1, avg_days_late: late, paid_invoices: 3, written_off: 0, reliability: rel })
const rows = [row('c1', 'Yeoman Roasters', 500, 'amber'), row('c2', 'acme', 1500, 'green', 2), row('c3', 'Brightwater', 0, null, null), row('c4', 'Zed Co', 900, 'red', 40)]

describe('company helpers', () => {
  it('reads company from the query with the demo default', () => {
    expect(currentCompany('')).toBe('company-020')
    expect(currentCompany('?company=company-007')).toBe('company-007')
  })
  it('only appends company when it is not the default', () => {
    expect(withCompany('/reports', 'company-020')).toBe('/reports')
    expect(withCompany('/reports', 'company-007')).toBe('/reports?company=company-007')
    expect(withCompany('/?run=r1&live', 'company-007')).toBe('/?run=r1&live&company=company-007')
    expect(chatUrl('r 1', 'company-020')).toBe('/?run=r%201&live')
  })
})

describe('formatting', () => {
  it('formats money like Home', () => {
    expect(money(1234.4)).toBe('$1,234')
    expect(money(-7457)).toBe('−$7,457')
    expect(money(null)).toBe('—')
    expect(cents(338.04)).toBe('$338.04')
  })
  it('labels rails honestly', () => {
    expect(railLabel('card')).toBe('Visa sandbox')
    expect(railLabel('visa')).toBe('Visa sandbox')
    expect(railLabel('usdc')).toBe('Solana devnet')
    expect(railLabel('solana')).toBe('Solana devnet')
  })
  it('reads rail readiness from /health', () => {
    const r = railReadiness({ visa: 'simulated', solana: 'unconfigured' })
    expect(r.visa.ok).toBe(false); expect(r.visa.label).toBe('Card payments simulated')
    expect(r.solana.ok).toBe(false)
    const ok = railReadiness({ visa: 'sandbox', solana: 'devnet' })
    expect(ok.visa.ok && ok.solana.ok).toBe(true)
  })
  it('shortens long references', () => {
    expect(shortRef(null)).toBe('—')
    expect(shortRef('abc')).toBe('abc')
    expect(shortRef('a'.repeat(10) + 'b'.repeat(10))).toBe('aaaaaaaa…bbbbbbbb')
  })
  it('strips markdown from answers', () => {
    expect(plainText('Top **$1,051.68** in `overdue`\n## Next')).toBe('Top $1,051.68 in overdue Next')
    expect(plainText(null)).toBe('')
  })
  it('renders relative times', () => {
    const now = Date.parse('2026-10-18T12:00:00Z')
    expect(ago('2026-10-18T11:59:50Z', now)).toBe('just now')
    expect(ago('2026-10-18T11:30:00Z', now)).toBe('30 min ago')
    expect(ago('2026-10-18T09:00:00Z', now)).toBe('3 h ago')
    expect(ago(null, now)).toBe('—')
  })
  it('colours history bars', () => {
    expect(historyTone({ status: 'paid', days_late: 3 })).toBe('green')
    expect(historyTone({ status: 'paid', days_late: 20 })).toBe('amber')
    expect(historyTone({ status: 'paid', days_late: 45 })).toBe('red')
    expect(historyTone({ status: 'written_off', days_late: null })).toBe('red')
    expect(historyTone({ status: 'open', days_late: null })).toBe('grey')
  })
})

describe('customer table', () => {
  it('filters by name case-insensitively', () => {
    expect(filterCustomers(rows, 'BRIGHT').map(r => r.id)).toEqual(['c3'])
    expect(filterCustomers(rows, '  ')).toBe(rows)
  })
  it('sorts numbers both ways', () => {
    expect(sortCustomers(rows, 'open_balance', 'desc').map(r => r.id)).toEqual(['c2', 'c4', 'c1', 'c3'])
    expect(sortCustomers(rows, 'open_balance', 'asc').map(r => r.id)).toEqual(['c3', 'c1', 'c4', 'c2'])
  })
  it('sorts names case-insensitively', () => {
    expect(sortCustomers(rows, 'display_name', 'asc').map(r => r.id)).toEqual(['c2', 'c3', 'c1', 'c4'])
  })
  it('keeps nulls last regardless of direction', () => {
    expect(sortCustomers(rows, 'reliability', 'asc').map(r => r.id)).toEqual(['c2', 'c1', 'c4', 'c3'])
    expect(sortCustomers(rows, 'reliability', 'desc').map(r => r.id)).toEqual(['c4', 'c1', 'c2', 'c3'])
    expect(sortCustomers(rows, 'avg_days_late', 'asc').at(-1)?.id).toBe('c3')
  })
  it('does not mutate the input', () => {
    const copy = rows.slice(); sortCustomers(rows, 'open_balance', 'asc'); expect(rows).toEqual(copy)
  })
  it('picks a sensible default direction', () => {
    expect(defaultDir('display_name')).toBe('asc')
    expect(defaultDir('open_balance')).toBe('desc')
  })
})
