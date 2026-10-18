import { useEffect, useState, type ReactNode } from 'react'
import { getCompanies, startRun } from './api'
import { chatUrl, withCompany } from './pageUtils'
import { ICONS } from './icons'
import './pages.css'

const BRAND = (import.meta.env.VITE_BRAND as string) || 'Span'

export type ShellPage = 'ask' | 'home' | 'get-paid' | 'reports' | 'customers'

/** Shared top bar + left rail for the Get paid / Reports / Customers pages. `.main` is the scroll container. */
export function Shell({ active, company, children, testId }: { active: ShellPage; company: string; children: ReactNode; testId?: string }) {
  const [name, setName] = useState<string>('')
  const [q, setQ] = useState('')
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    let stale = false
    getCompanies().then(cs => { if (!stale) setName(cs.find(c => c.id === company)?.name || company) }).catch(() => { if (!stale) setName(company) })
    return () => { stale = true }
  }, [company])
  const ask = async () => {
    const text = q.trim(); if (!text || asking) return
    setAsking(true)
    try { const { run_id } = await startRun(company, text); location.assign(chatUrl(run_id, company)) }
    catch { setAsking(false) }
  }
  const items: [ShellPage, string, ReactNode, string][] = [
    ['ask', '/', ICONS.chat, 'Ask'], ['home', '/home', ICONS.book, 'Home'], ['get-paid', '/get-paid', ICONS.card, 'Get paid'],
    ['reports', '/reports', ICONS.trend, 'Reports'], ['customers', '/customers', ICONS.person, 'Customers'],
  ]
  return <div className="app">
    <header className="topbar">
      <div className="brand"><img className="mark" src="/logo.png" alt="" /><div className="name">{BRAND.toLowerCase()}</div></div>
      <div className="company">{name || 'Loading…'}</div>
      <div className="search"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="5"/><path d="M11 11l3.5 3.5"/></svg><input placeholder={asking ? 'Starting…' : 'Ask about your money, or search transactions, customers, reports'} aria-label={`Ask ${BRAND}`} value={q} disabled={asking} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void ask() }} /></div>
      <div className="status"><i className="dot" />Live</div>
    </header>
    <div className="body">
      <nav className="rail">
        {items.map(([id, path, icon, label]) => <a key={id} className={id === active ? 'on' : undefined} aria-current={id === active ? 'page' : undefined} href={id === 'ask' ? withCompany('/', company) : withCompany(path, company)}>{icon}{label}</a>)}
      </nav>
      <main className="main pg" data-testid={testId}>{children}</main>
    </div>
  </div>
}

export function Loading({ label = 'loading' }: { label?: string }) {
  return <div className="thinking pg-loading"><i/><i/><i/> {label}</div>
}
export function ErrorCard({ what, error, onRetry }: { what: string; error: string; onRetry: () => void }) {
  return <div className="card err" role="alert">{what} didn’t load: {error}<button className="btn" style={{ height: 28, marginLeft: 'auto' }} onClick={onRetry}>Retry</button></div>
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="pg-empty"><b>{title}</b>{children && <div className="fine">{children}</div>}</div>
}
export function PageHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return <div className="pg-head">
    <div><h1 className="q" style={{ margin: 0 }}>{title}</h1>{sub && <div className="eyebrow" style={{ margin: '4px 0 0' }}>{sub}</div>}</div>
    {right}
  </div>
}
