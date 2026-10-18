import { test } from 'node:test'
import assert from 'node:assert/strict'
import { descendants, runIngestor } from '../src/branches.ts'
import { emptyRun, reduce } from '../src/events.ts'
import type { RawEvent } from '../src/types.ts'

test('accepts all child events, deduplicates replay/SSE, excludes unrelated runs', () => {
  const received: RawEvent[] = []
  const stream = runIngestor(event => received.push(event))
  stream.add('root')
  const events = [
    { event: 'run.start', data: { id: '1', run_id: 'root' } },
    { event: 'run.start', data: { id: '2', run_id: 'child', parent_run_id: 'root' } },
    { event: 'node.create', data: { id: '3', run_id: 'child', node_id: 'n1' } },
    { event: 'node.update', data: { id: '4', run_id: 'child', node_id: 'n1' } },
    { event: 'run.start', data: { id: '5', run_id: 'unrelated' } },
  ]
  events.forEach(stream.ingest)
  events.forEach(stream.ingest)
  assert.deepEqual(received.map(event => event.data.id), ['1', '2', '3', '4'])
})

test('saved threads discover all descendants independent of list order', () => {
  assert.deepEqual(new Set(descendants('root', [
    { run_id: 'grandchild', parent_run_id: 'child' },
    { run_id: 'unrelated' }, { run_id: 'root' },
    { run_id: 'child', parent_run_id: 'root' },
    { run_id: 'sibling', parent_run_id: 'root' },
  ])), new Set(['child', 'sibling', 'grandchild']))
})

test('cross-run node references remain qualified even when local IDs repeat', () => {
  let child = reduce(emptyRun(), { event: 'run.start', data: { run_id: 'child', parent_run_id: 'root' } })
  child = reduce(child, { event: 'node.create', data: {
    node_id: 'n1', type: 'context', parent: 'n1', parent_run_id: 'root',
    data: { reused_from: { run_id: 'root', node_id: 'n1' } },
  } })
  child = reduce(child, { event: 'node.update', data: { node_id: 'n1', data: { bank_balance: 6533.65 } } })
  assert.equal(child.parent_run_id, 'root')
  assert.equal(child.nodes.n1.parent_run_id, 'root')
  assert.deepEqual(child.nodes.n1.data.reused_from, { run_id: 'root', node_id: 'n1' })
})

test('late branch retains its one scoring node and server-sorted invoice rows', () => {
  let run = reduce(emptyRun(), { event: 'run.start', data: { run_id: 'late', parent_run_id: 'root' } })
  run = reduce(run, { event: 'node.create', data: { node_id: 'late-scoring', type: 'scoring', data: { overdue_only: true } } })
  for (const days of [100, 60, 3]) run = reduce(run, { event: 'node.update', data: { node_id: 'late-scoring', row: { days_past_due: days } } })
  assert.deepEqual(run.order, ['late-scoring'])
  assert.equal(run.nodes['late-scoring'].data.overdue_only, true)
  assert.deepEqual(run.nodes['late-scoring'].rows.map(row => row.days_past_due), [100, 60, 3])
})
