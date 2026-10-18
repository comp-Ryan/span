import type { RawEvent } from './types'

export function descendants(root: string, runs: { run_id: string; parent_run_id?: string }[]) {
  const known = new Set([root])
  let changed = true
  while (changed) {
    changed = false
    for (const run of runs) if (run.parent_run_id && known.has(run.parent_run_id) && !known.has(run.run_id)) {
      known.add(run.run_id); changed = true
    }
  }
  return [...known].filter(id => id !== root)
}

/** Every event after a child's run.start belongs to the child, not only its start. */
export function runIngestor(onEvent: (event: RawEvent) => void) {
  const accepted = new Set<string>(), seen = new Set<string>()
  return {
    add: (id: string) => { accepted.add(id) },
    ingest: (event: RawEvent) => {
      const d = event.data
      if (event.event === 'run.start' && d.parent_run_id && accepted.has(d.parent_run_id)) accepted.add(d.run_id)
      if (!accepted.has(d.run_id) || (d.id && seen.has(d.id))) return
      if (d.id) seen.add(d.id)
      onEvent(event)
    },
  }
}
