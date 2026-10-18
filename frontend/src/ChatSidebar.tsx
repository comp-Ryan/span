import { useEffect, useRef, useState } from 'react'
import { getRuns } from './api'
import { ago, chatUrl, plainText } from './pageUtils'
import { readChatTitle, rootChats, writeChatTitle } from './chatHistory'
import type { RunSummary } from './types'

export default function ChatSidebar({ company, active, revision, onRename }: { company: string; active?: string; revision: string; onRename: (id: string, title: string) => void }) {
  const navigateTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(navigateTimer.current), [])
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<string>()
  const [draft, setDraft] = useState('')
  const [, refresh] = useState(0)
  useEffect(() => {
    let cancelled = false
    const load = () => getRuns(company).then(rows => { if (!cancelled) { setRuns(rootChats(rows, active)); setError('') } }).catch(() => { if (!cancelled) setError('Chat history unavailable') })
    void load(); const timer = setInterval(load, 15000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [company, revision, active])
  const save = (id: string) => {
    try { const title = writeChatTitle(company, id, draft); onRename(id, title); refresh(n => n + 1); setEditing(undefined) }
    catch { setError('Your browser could not save this name') }
  }
  return <aside className="chat-sidebar" aria-label="Chat history">
    <a className="btn new-chat" href={`/?live&new=1&company=${encodeURIComponent(company)}`}>+ New chat</a>
    <h2>Past chats</h2>
    {error && <div role="alert" className="fine">{error}</div>}
    {!error && !runs.length && <p className="fine">Your conversations will appear here.</p>}
    {runs.map(run => <div key={run.run_id} className={`chat-history-item ${active === run.run_id ? 'active' : ''}`}>
      {editing === run.run_id ? <form onSubmit={e => { e.preventDefault(); save(run.run_id) }}><input autoFocus aria-label="Rename past chat" value={draft} onChange={e => setDraft(e.target.value)} onBlur={() => save(run.run_id)} onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); setEditing(undefined) } }} /></form> : <>
        <a href={chatUrl(run.run_id, company)} onClick={e => { if (e.detail === 0) return; e.preventDefault(); clearTimeout(navigateTimer.current); navigateTimer.current = setTimeout(() => { location.href = chatUrl(run.run_id, company) }, 300) }} onDoubleClick={e => { e.preventDefault(); clearTimeout(navigateTimer.current); setDraft(readChatTitle(company, run.run_id) || run.question); setEditing(run.run_id) }}>{readChatTitle(company, run.run_id) || run.question || 'General chat'}</a>
        <button className="chat-rename" aria-label={`Rename ${run.question}`} onClick={() => { setDraft(readChatTitle(company, run.run_id) || run.question); setEditing(run.run_id) }}>✎</button>
      </>}
      <span className="fine">{plainText(run.answer_title) || (run.status === 'open' ? 'In progress' : 'Finished')}</span>
      <time className="fine" dateTime={run.started_at}>{ago(run.started_at)}</time>
    </div>)}
  </aside>
}
