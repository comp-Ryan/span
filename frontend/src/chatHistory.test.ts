import { describe, expect, it } from 'vitest'
import { chatTitleKey, readChatTitle, rootChats, writeChatTitle } from './chatHistory'
import type { RunSummary } from './types'
describe('chat history', () => {
  it('lists only roots newest first without mutating source', () => {
    const runs = [{ run_id: 'a', question: 'Am I okay?', started_at: '2026-10-01' }, { run_id: 'child', parent_run_id: 'a', question: 'And next month?', started_at: '2026-10-03' }, { run_id: 'b', question: 'Who should I chase today?', started_at: '2026-10-02' }] as RunSummary[]
    expect(rootChats(runs).map(r => r.run_id)).toEqual(['b', 'a'])
    expect(runs[0].run_id).toBe('a')
  })
  it('keeps titles per company and root, and never changes another chat', () => {
    const data = new Map<string, string>()
    const store = { getItem: (k: string) => data.get(k) || null, setItem: (k: string, v: string) => data.set(k, v) }
    expect(writeChatTitle('c1', 'r1', '  Payroll  ', store)).toBe('Payroll')
    expect(readChatTitle('c1', 'r1', store)).toBe('Payroll')
    expect(readChatTitle('c2', 'r1', store)).toBeNull()
    expect(readChatTitle('c1', 'r2', store)).toBeNull()
    expect(chatTitleKey('c1', 'r1')).not.toBe('span.chatTitle')
    expect(writeChatTitle('c1', 'r1', ' ', store)).toBe('General chat')
  })
})

describe('repeated questions', () => {
  const run = (id: string, question: string, started_at: string, parent?: string) => ({ run_id: id, question, started_at, parent_run_id: parent, status: 'closed', source: 'web' } as any)
  it('shows one entry per question, the newest run, so test batteries do not fill the sidebar', () => {
    const runs = [run('a', 'Who should I chase today?', '2026-10-18T01:00:00Z'), run('b', 'who should I chase today? ', '2026-10-18T03:00:00Z'), run('c', 'Am I okay?', '2026-10-18T02:00:00Z')]
    expect(rootChats(runs).map(r => r.run_id)).toEqual(['b', 'c'])
  })
  it('always keeps the chat that is open, even when a newer run asked the same thing', () => {
    const runs = [run('a', 'Who should I chase today?', '2026-10-18T01:00:00Z'), run('b', 'Who should I chase today?', '2026-10-18T03:00:00Z')]
    expect(rootChats(runs, 'a').map(r => r.run_id)).toEqual(['a'])
    expect(rootChats(runs, 'b').map(r => r.run_id)).toEqual(['b'])
  })
  it('follow-ups never count as repeats of their root', () => {
    const runs = [run('a', 'Am I okay?', '2026-10-18T01:00:00Z'), run('f', 'Am I okay?', '2026-10-18T01:05:00Z', 'a')]
    expect(rootChats(runs).map(r => r.run_id)).toEqual(['a'])
  })
})
