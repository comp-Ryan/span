import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RawEvent } from './types'
const mocks = vi.hoisted(() => ({ startRun: vi.fn(), replay: vi.fn(), subscribe: vi.fn(), off: vi.fn() }))
vi.mock('./api', () => mocks)
import { connectLive } from './live'
describe('fresh chat subscription', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.subscribe.mockReturnValue(mocks.off) })
  it('does not auto-run and replays the newly started root without losing SSE branches', async () => {
    const received: RawEvent[] = []
    const stop = connectLive('company-020', null, e => received.push(e), e => { throw e }, false, true)
    expect(mocks.startRun).not.toHaveBeenCalled()
    mocks.replay.mockResolvedValue([{ event: 'run.start', data: { id: '1', run_id: 'new' } }])
    await stop.watch('new')
    const push = mocks.subscribe.mock.calls[0][1]
    push({ event: 'run.start', data: { id: '2', run_id: 'child', parent_run_id: 'new' } })
    push({ event: 'node.create', data: { id: '3', run_id: 'child', node_id: 'tool-1' } })
    push({ event: 'run.start', data: { id: '4', run_id: 'unrelated' } })
    expect(received.map(e => e.data.id)).toEqual(['1', '2', '3'])
    stop(); expect(mocks.off).toHaveBeenCalledOnce()
  })
})

it('buffers SSE while a newly started root replays, so a node cannot arrive before run.start', async () => {
  const received: RawEvent[] = []
  mocks.subscribe.mockReturnValue(mocks.off)
  const stop = connectLive('company-020', null, e => received.push(e), e => { throw e }, false, true)
  const push = mocks.subscribe.mock.calls.at(-1)![1]
  const node = { event: 'node.create', data: { id: '2', run_id: 'new', node_id: 'tool-1' } }
  mocks.replay.mockImplementation(async () => {
    push(node)
    expect(received).toEqual([])
    return [{ event: 'run.start', data: { id: '1', run_id: 'new' } }, node]
  })
  await stop.watch('new')
  expect(received.map(e => e.data.id)).toEqual(['1', '2'])
  stop()
})

it('never starts a question on its own: opening the Ask page without a run just listens', async () => {
  const received: RawEvent[] = []
  mocks.subscribe.mockReturnValue(mocks.off)
  const stop = connectLive('company-020', null, e => received.push(e), e => { throw e })  // not marked fresh, no saved run
  await new Promise(r => setTimeout(r, 0))
  expect(mocks.startRun).not.toHaveBeenCalled()
  expect(mocks.replay).not.toHaveBeenCalled()
  stop()
})
