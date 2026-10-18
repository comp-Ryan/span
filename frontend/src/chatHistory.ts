import type { RunSummary } from './types'
export const chatTitleKey = (company: string, run: string) => `span.chatTitle:${company}:${run}`
export const rootChats = (runs: RunSummary[]) => runs.filter(r => !r.parent_run_id).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at))
export function readChatTitle(company: string, run: string, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage): string | null {
  try { return storage.getItem(chatTitleKey(company, run)) } catch { return null }
}
export function writeChatTitle(company: string, run: string, title: string, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage) {
  const value = title.trim() || 'General chat'
  storage.setItem(chatTitleKey(company, run), value)
  return value
}
