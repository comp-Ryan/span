import { useCallback, useEffect, useState } from 'react'
import { Shell, Loading } from './Shell'
import { getSponsorChecks } from './api'
import type { SponsorCheck, SponsorChecks } from './types'
import { ICONS } from './icons'
import { currentCompany } from './pageUtils'

const LABEL: Record<SponsorCheck['status'], string> = { pass: 'Answering', warn: 'Degraded', fail: 'Not answering', off: 'Fallback', info: 'Build tool' }
const ORDER: SponsorCheck['status'][] = ['pass', 'warn', 'fail', 'off', 'info']

/** Every integration, checked live: what is wired, what is configured, and what answers right now. */
export default function Sponsors() {
  const company = currentCompany()
  const [data, setData] = useState<SponsorChecks | null>(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const run = useCallback(async () => {
    setRunning(true); setError('')
    try { setData(await getSponsorChecks()) } catch (e) { setError(String(e)) } finally { setRunning(false) }
  }, [])
  useEffect(() => { void run() }, [run])
  const checks = data ? [...data.checks].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status)) : []
  return <Shell active="sponsors" company={company} testId="sponsors-page">
    <div className="pg-head">
      <div>
        <h1 className="q">Integrations</h1>
        <p className="fine">Each sponsor integration is called live from this backend. Green answers now; grey means the product runs its labeled fallback instead. No keys are shown.</p>
      </div>
      <button className="btn primary" onClick={() => void run()} disabled={running}>{running ? 'Checking…' : 'Run checks again'}</button>
    </div>
    {error && <div role="alert">{error}</div>}
    {data && <div className="sponsor-summary">
      {ORDER.map(s => data.summary[s] ? <span key={s} className={`spill ${s}`}>{data.summary[s]} {LABEL[s].toLowerCase()}</span> : null)}
      <span className="fine">checked {new Date(data.generated_at).toLocaleTimeString()}</span>
    </div>}
    {!data && !error && <Loading label="calling every integration" />}
    {data && <table className="sponsors" data-testid="sponsor-table">
      <thead><tr><th>Integration</th><th>Role</th><th>Status</th><th>What it said</th><th className="num">ms</th></tr></thead>
      <tbody>
        {checks.map(c => <tr key={c.name} className={c.status}>
          <td><b>{c.name}</b></td>
          <td className="fine">{c.track}</td>
          <td><span className={`spill ${c.status}`}>{c.status === 'pass' ? ICONS.check : null}{LABEL[c.status]}</span></td>
          <td>{c.detail}</td>
          <td className="num fine">{c.ms.toLocaleString()}</td>
        </tr>)}
      </tbody>
    </table>}
  </Shell>
}
