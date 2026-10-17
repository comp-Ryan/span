import { useEffect, useState } from 'react'
import { money } from './events'

type Day = { date: string; inflow: number; outflow: number; balance: number }
type Cash = { start: string; target: string; opening_balance: number; days: Day[]; pessimistic_days: Day[]; payroll_dates: string[] }

/** Live mode draws API numbers only; failed requests never substitute a synthetic line. */
export default function DailyCashChart({ company, target, revision, neverPays }: { company: string; target: string; revision: number; neverPays?: string }) {
  const [cash, setCash] = useState<Cash | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const abort = new AbortController()
    const query = new URLSearchParams({ company, target })
    if (neverPays) query.set('never_pays', neverPays)
    fetch(`/api/cash?${query}`, { signal: abort.signal }).then(async r => {
      if (!r.ok) throw new Error('Cash projection unavailable')
      return r.json() as Promise<Cash>
    }).then(value => { setCash(value); setError('') }).catch(e => { if (e.name !== 'AbortError') setError(e.message) })
    return () => abort.abort()
  }, [company, target, revision, neverPays])
  if (error) return <div className="chart" role="alert">{error}</div>
  if (!cash) return <div className="chart">Loading dated cash projection…</div>
  const W = 1100, H = 200, bottom = 165, top = 22
  const all = [...cash.days, ...cash.pessimistic_days].map(d => d.balance)
  const lo = Math.min(0, ...all), hi = Math.max(1, ...all)
  const y = (v: number) => bottom - (v - lo) / (hi - lo) * (bottom - top)
  const x = (i: number) => 8 + i / Math.max(1, cash.days.length - 1) * (W - 16)
  const path = (days: Day[]) => days.map((d, i) => `${i ? 'L' : 'M'}${x(i)} ${y(d.balance)}`).join(' ')
  return <div className="chart" data-testid="daily-cash-chart">
    <div className="head"><b>Cash in the bank, day by day</b><div className="legend"><span>Green: expected receipts</span><span>Orange: payers below 70% slip</span></div></div>
    <svg viewBox={`0 0 ${W} ${H}`} fill="none" role="img" aria-label="Server-projected expected and pessimistic cash balances">
      <path d={`M0 ${y(0)} H${W}`} stroke="#D52B1E" strokeDasharray="4 4" />
      {cash.payroll_dates.map(day => { const i = cash.days.findIndex(d => d.date === day); return <path key={day} d={`M${x(i)} ${top} V${bottom}`} stroke="#8D9096" strokeDasharray="3 4"><title>{day}: payroll</title></path> })}
      <path d={path(cash.days)} stroke="#2CA01C" strokeWidth="2.5" />
      <path d={path(cash.pessimistic_days)} stroke="#E08A00" strokeWidth="2" strokeDasharray="5 4" />
      {cash.days.map((d, i) => <circle key={d.date} cx={x(i)} cy={y(d.balance)} r="3" fill="#2CA01C"><title>{d.date}: {money(d.balance)} · in {money(d.inflow)} · out {money(d.outflow)}</title></circle>)}
      <text x="8" y="193" fill="#6B6C72" fontSize="12">{cash.start} · opening {money(cash.opening_balance)}</text>
      <text x={W - 8} y="193" textAnchor="end" fill="#393A3D" fontSize="12">{cash.target} · expected {money(cash.days.at(-1)?.balance)} · pessimistic {money(cash.pessimistic_days.at(-1)?.balance)}</text>
    </svg>
    <div className="fine">Dataset clock · balances after payroll and bills · receipts on model-predicted dates, weighted by payment probability.</div>
  </div>
}
