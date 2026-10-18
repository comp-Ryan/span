import { describe, expect, it } from 'vitest'
import { chatTitleKey, readChatTitle, rootChats, writeChatTitle } from './chatHistory'
import type { RunSummary } from './types'
describe('chat history', () => {
  it('lists only roots newest first without mutating source', () => {
    const runs = [{ run_id: 'a', started_at: '2026-10-01' }, { run_id: 'child', parent_run_id: 'a', started_at: '2026-10-03' }, { run_id: 'b', started_at: '2026-10-02' }] as RunSummary[]
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
