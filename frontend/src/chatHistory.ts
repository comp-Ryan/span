import type { RunSummary } from './types'
export const chatTitleKey = (company: string, run: string) => `span.chatTitle:${company}:${run}`
const sameQuestion = (q: string) => q.trim().toLowerCase().replace(/\s+/g, ' ')
/** Root conversations, newest first, one per question: a repeated question shows its newest run (the open chat `keep` always stays). */
export const rootChats = (runs: RunSummary[], keep?: string) => {
  const sorted = runs.filter(r => !r.parent_run_id).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
  const seen = new Set<string>()
  if (keep) { const k = sorted.find(r => r.run_id === keep); if (k) seen.add(sameQuestion(k.question || '')) }
  return sorted.filter(r => {
    if (r.run_id === keep) return true
    const key = sameQuestion(r.question || '')
    if (seen.has(key)) return false
    seen.add(key); return true
  })
}
export function readChatTitle(company: string, run: string, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage): string | null {
  try { return storage.getItem(chatTitleKey(company, run)) } catch { return null }
}
export function writeChatTitle(company: string, run: string, title: string, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage) {
  const value = title.trim() || 'General chat'
  storage.setItem(chatTitleKey(company, run), value)
  return value
}
