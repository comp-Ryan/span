import { useState } from 'react'
import { generateReport, getReports } from './api'
import { verdictTone } from './Home'
import { Empty, ErrorCard, Loading, PageHead, Shell } from './Shell'
import { ICONS } from './icons'
import { useLoad } from './useLoad'
import { ago, chatUrl, currentCompany, fmtDateTime, plainText } from './pageUtils'

const reportUrl = (id: string, company: string) => `/report/${encodeURIComponent(id)}?company=${encodeURIComponent(company)}`
const pdfUrl = (id: string, company: string) => `/api/reports/${encodeURIComponent(id)}.pdf?company=${encodeURIComponent(company)}`

export default function Reports() {
  const company = currentCompany()
  const res = useLoad(() => getReports(company), company)
  const [busy, setBusy] = useState<Record<string, 'working' | 'failed'>>({})
  const d = res.data
  const loading = !d && res.loading

  const generate = async (runId: string) => {
    setBusy(b => ({ ...b, [runId]: 'working' }))
    try {
      const r = await generateReport(runId, company)
      if (!r?.report_id) throw new Error('failed')
      setBusy(b => { const { [runId]: _done, ...rest } = b; return rest })
      res.reload()
    } catch { setBusy(b => ({ ...b, [runId]: 'failed' })) }
  }

  return <Shell active="reports" company={company} testId="reports">
    <PageHead title="Reports" sub={<span>One-page write-ups of each answered question, ready to print or send to your accountant.</span>} />
    {res.error && <ErrorCard what="Reports" error={res.error} onRetry={res.reload} />}
    {!(res.error && !d) && <>

    <section className="card pg-sec" data-testid="report-list">
      <div className="head"><b>Generated reports</b><span className="fine">{d ? `${d.reports.length} report${d.reports.length === 1 ? '' : 's'}` : ''}</span></div>
      {loading ? <Loading /> : d && d.reports.length === 0 ? <Empty title="No reports yet">Every chat that reaches an answer can become a one-pager. Ask a question, or generate one from a chat below.</Empty> : d && <div className="rep-list">
        {d.reports.map(r => <div key={r.report_id} className="rep-row">
          <span className="ic grey" style={{ width: 28, height: 28 }}>{ICONS.doc}</span>
          <div className="rep-main">
            <a className="rep-q" href={reportUrl(r.report_id, company)}>{r.question}</a>
            <div className="rep-a"><span className={`pill-v ${verdictTone(r.answer)}`} title={plainText(r.answer)}>{plainText(r.answer) || 'No answer recorded'}</span></div>
          </div>
          <span className="fine when" title={fmtDateTime(r.generated_at)}>{ago(r.generated_at)}</span>
          <div className="rep-act">
            <a className="btn sm" href={reportUrl(r.report_id, company)}>Open</a>
            <a className="btn sm" href={pdfUrl(r.report_id, company)} target="_blank" rel="noreferrer">PDF</a>
          </div>
        </div>)}
      </div>}
    </section>

    <section className="card pg-sec" data-testid="unreported">
      <div className="head"><b>Chats without a report</b><span className="fine">Finished chats that never got a one-pager.</span></div>
      {loading ? <Loading /> : d && d.unreported.length === 0 ? <Empty title="All caught up">Every finished chat has a report.</Empty> : d && <div className="rep-list">
        {d.unreported.map(u => <div key={u.run_id} className="rep-row">
          <span className="ic grey" style={{ width: 28, height: 28 }}>{ICONS.chat}</span>
          <div className="rep-main">
            <a className="rep-q" href={chatUrl(u.run_id, company)}>{u.question}</a>
            <div className="rep-a"><span className={`pill-v ${verdictTone(u.answer_title)}`} title={plainText(u.answer_title) || undefined}>{plainText(u.answer_title) || 'No answer'}</span></div>
          </div>
          <span className="fine when" title={fmtDateTime(u.started_at)}>{ago(u.started_at)}</span>
          <div className="rep-act">
            {busy[u.run_id] === 'failed' && <span className="fine" role="alert" style={{ color: 'var(--red)' }}>Couldn’t generate</span>}
            <button className="btn sm primary" disabled={busy[u.run_id] === 'working'} onClick={() => generate(u.run_id)}>{busy[u.run_id] === 'working' ? 'Generating…' : busy[u.run_id] === 'failed' ? 'Try again' : 'Generate report'}</button>
          </div>
        </div>)}
      </div>}
    </section>
    </>}
  </Shell>
}
