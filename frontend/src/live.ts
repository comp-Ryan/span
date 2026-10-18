import type { RawEvent } from './types'
import { replay, startRun, subscribe } from './api'
import { descendants, runIngestor } from './branches'

/** Subscribe before replaying so the handoff cannot lose a newly created branch. */
export function connectLive(company: string, savedRun: string | null, onEvent: (event: RawEvent) => void, onError: (error: unknown) => void) {
  let cancelled = false, ready = false
  const pending: RawEvent[] = []
  const accept = runIngestor(onEvent)
  const off = subscribe(company, event => ready ? accept.ingest(event) : pending.push(event))
  ;(async () => {
    try {
      const root = savedRun ? { run_id: savedRun } : await startRun(company, 'Am I going to make payroll these next two weeks?')
      accept.add(root.run_id)
      const history = await replay(root.run_id, company)
      // SSE's bounded initial replay is not a complete history of older branches.
      if (savedRun) {
        const response = await fetch(`/api/runs?company=${encodeURIComponent(company)}`)
        if (!response.ok) throw new Error('Could not load follow-up threads')
        const { runs } = await response.json() as { runs: { run_id: string; parent_run_id?: string }[] }
        const children = descendants(root.run_id, runs)
        children.forEach(accept.add)
        for (const child of children) history.push(...await replay(child, company))
      }
      if (cancelled) return
      ;[...history, ...pending].sort((a, b) => Number(a.data.id) - Number(b.data.id)).forEach(accept.ingest)
      pending.length = 0
      ready = true
    } catch (error) { if (!cancelled) onError(error) }
  })()
  return () => { cancelled = true; off() }
}
