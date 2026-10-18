import { describe, expect, it } from 'vitest'
import fixture from '../public/fixture.json'
import { emptyRun, k, money, reduce } from './events'
import type { RawEvent, RunState } from './types'

const events = fixture.events as RawEvent[]
const at = (ev: RawEvent) => (ev.ts_offset_s ?? 0) * 1000
const replay = (evs: RawEvent[] = events) => evs.reduce((run, ev) => reduce(run, ev, at(ev)), emptyRun())

describe('reduce over fixture.json', () => {
  const run = replay()

  it('builds the run header from run.start and closes with run.end and report.ready', () => {
    expect(run.run_id).toBe('run-demo-020')
    expect(run.question).toBe(fixture.meta.question)
    expect(run.source).toBe('call')
    expect(run.startedAt).toBe(0)
    expect(run.status).toBe('open')
    expect(run.report_id).toBe('rep-demo-020')
  })

  it('creates every node once, in order, with the contract edges', () => {
    expect(run.order).toEqual(['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7', 'n8', 'n9', 'n10', 'n12'])
    expect(run.order.map(id => run.nodes[id].parent)).toEqual([null, 'n1', 'n2', 'n3', 'n4', 'n5', 'n5', 'n5', 'n6', 'n9', 'n10'])
    expect(run.order.map(id => run.nodes[id].type)).toEqual(
      ['context', 'scoring', 'forecast', 'answer', 'levers', 'action', 'action', 'action', 'action', 'action', 'action'])
    expect(Object.values(run.nodes).every(n => n.status === 'done')).toBe(true)
  })

  it('accumulates scoring rows and progress', () => {
    const n2 = run.nodes.n2
    expect(n2.rows).toHaveLength(204)
    expect(n2.progress).toEqual({ done: 204, total: 204 })
    expect(n2.rows[0]).toMatchObject({ invoice_id: 'inv-03396', band: 'green', source: 'owed_model' })
    expect(n2.createdAt).toBe(600)
    expect(n2.doneAt).toBe(6770)
  })

  it('keeps the first forecast as the baseline when a payment updates it', () => {
    const n3 = run.nodes.n3.data
    expect(n3.cash_at_target).toBe(193.16)
    expect(n3.gap).toBe(0)
    expect(n3.initial_cash_at_target).toBe(-384.94)
    expect(n3.initial_need).toBe(24141.86)
  })

  it('merges node data and collects negotiation rounds', () => {
    expect(run.nodes.n6.data).toMatchObject({ kind: 'reminder', reminder_id: 'rem-0001' })
    const n10 = run.nodes.n10
    expect(n10.rounds.map(r => r.from)).toEqual(['owed', 'customer'])
    expect(n10.data.agreement.installments).toHaveLength(2)
    expect(n10.data.round).toEqual(n10.rounds[1])
  })

  it('records decisions with their timeout and default', () => {
    expect(Object.keys(run.decisions)).toEqual(['d1', 'd2'])
    expect(run.decisions.d1).toMatchObject({ node_id: 'n5', prompt: 'Text them?', auto_resolves_in_s: null })
    expect(run.decisions.d1.options.map(o => o.id)).toEqual(['yes', 'chase_only', 'no'])
    expect(run.decisions.d2).toMatchObject({ node_id: 'n10', auto_resolves_in_s: 8, default: 'accept' })
    expect(run.decisions.d2.resolved).toBeUndefined()
  })

  it('writes the iMessage transcript: question, tool steps with timings, spoken answers', () => {
    expect(run.turns[0]).toEqual({ kind: 'you', text: fixture.meta.question, at: 0 })
    const tools = run.turns.filter(t => t.kind === 'tool')
    expect(tools.slice(0, 3)).toEqual([
      { kind: 'tool', text: 'read books', meta: 'bank $6.5k, payroll $13.3k, bills $10.9k', secs: 0.4, at: 100 },
      { kind: 'tool', text: 'score invoices', meta: '204 scored', secs: expect.closeTo(6.17, 5), at: 600 },
      { kind: 'tool', text: 'forecast cash', meta: 'cushion $-385', secs: expect.closeTo(0.5, 5), at: 6820 },
    ])
    expect(tools[3]).toMatchObject({ text: 'find levers', meta: 'Text 3 reliable late payers, Slide 2 tolerant vendor bills a week, Hold owner draw this month' })
    expect(tools.slice(4).map(t => [t.text, t.meta])).toEqual([
      ['Texting Evergreen Juniper Flats Removals', 'reminder'], ['Texting Hearth Trading Partners', 'reminder'],
      ['Texting Okonkwo & Daughters Roasters', 'reminder'], ['Evergreen replied', 'reply'],
      ["Negotiating with Evergreen's agent", 'negotiation'], ['Evergreen paid $578.10', 'payment']])
    const spoken = events.filter(e => e.event === 'speech').map(e => e.data.text)
    expect(run.turns.filter(t => t.kind === 'owed').map(t => t.text)).toEqual(spoken)
    expect(run.turns.some(t => t.kind === 'tool' && t.text === 'answer')).toBe(false)
  })

  it('never mutates earlier states', () => {
    const mid = replay(events.slice(0, 10))
    const snapshot = JSON.stringify(mid)
    events.slice(10).reduce((r, ev) => reduce(r, ev, at(ev)), mid)
    expect(JSON.stringify(mid)).toBe(snapshot)
    expect(mid.nodes.n2.rows.length).toBeLessThan(204)
  })
})

describe('reduce edge cases', () => {
  const base = reduce(emptyRun(), { event: 'run.start', run_id: 'r1', data: { question: 'q', parent_run_id: 'r0', company_id: 'company-020' } }, 5)

  it('starts a fresh run and carries the parent link', () => {
    expect(base).toMatchObject({ run_id: 'r1', parent_run_id: 'r0', company_id: 'company-020', status: 'open', startedAt: 5, order: [] })
  })

  it('ignores updates for unknown nodes and decisions, and unknown events', () => {
    for (const ev of [{ event: 'node.update', data: { node_id: 'zz', status: 'done' } },
      { event: 'decision.resolved', data: { decision_id: 'zz', option_id: 'yes' } }, { event: 'heartbeat', data: {} }])
      expect(reduce(base, ev)).toBe(base)
  })

  it('marks decisions resolved by option_id or resolved', () => {
    const withDecision = reduce(base, { event: 'decision', data: { decision_id: 'd', node_id: 'n5', prompt: 'p', options: [] } })
    expect(withDecision.decisions.d.auto_resolves_in_s).toBeNull()
    expect(reduce(withDecision, { event: 'decision.resolved', data: { decision_id: 'd', option_id: 'yes' } }).decisions.d.resolved).toBe('yes')
    expect(reduce(withDecision, { event: 'decision.resolved', data: { decision_id: 'd', resolved: 'no' } }).decisions.d.resolved).toBe('no')
  })

  it('marks failed nodes without a done time, and closes runs', () => {
    let run: RunState = reduce(base, { event: 'node.create', data: { node_id: 'tool-1', type: 'forecast', title: 'Forecast cash', parent: 'context' } }, 10)
    expect(run.nodes['tool-1'].status).toBe('running')
    run = reduce(run, { event: 'node.update', data: { node_id: 'tool-1', status: 'failed', data: { error: 'x' } } }, 20)
    expect(run.nodes['tool-1']).toMatchObject({ status: 'failed', doneAt: undefined, data: { error: 'x' } })
    expect(reduce(run, { event: 'run.end', data: { status: 'closed' } }).status).toBe('closed')
  })
})

describe('formatters', () => {
  it('abbreviates thousands and rounds dollars', () => {
    expect([k(undefined), k(999.6), k(1000), k(6533.65), k(-2500)]).toEqual(['—', '1000', '1k', '6.5k', '-2.5k'])
    expect([money(undefined), money(1234.5)]).toEqual(['—', '$1,235'])
  })
})
