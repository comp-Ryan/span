import type { RawEvent, ReportDoc } from './types'

const BASE = '/api'

export async function startRun(company: string, question: string, source = 'web', parentRunId?: string) {
  const r = await fetch(`${BASE}/ask?company=${encodeURIComponent(company)}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question, source, parent_run_id: parentRunId }) })
  if (!r.ok) throw new Error((await r.json()).error?.message || 'Request failed')
  return r.json() as Promise<{ run_id: string; intent: string }>
}
export async function resolveDecision(decisionId: string, optionId: string, company: string) {
  const r = await fetch(`${BASE}/decisions/${decisionId}?company=${encodeURIComponent(company)}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ option_id: optionId }) })
  if (!r.ok) throw new Error((await r.json()).error?.message || 'Request failed')
  return r.json()
}
export async function replay(runId: string, company?: string): Promise<RawEvent[]> {
  const r = await fetch(`${BASE}/runs/${runId}?company=${encodeURIComponent(company || "company-020")}`); const j = await r.json(); return j.events || []
}
export async function getReport(id: string): Promise<ReportDoc> {
  const r = await fetch(`${BASE}/reports/${encodeURIComponent(id)}`)
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}
export function subscribe(company: string, onEvent: (e: RawEvent) => void): () => void {
  const es = new EventSource(`${BASE}/events?company=${encodeURIComponent(company)}`)
  const kinds = ['run.start', 'node.create', 'node.update', 'decision', 'decision.resolved', 'speech', 'report.ready', 'run.end', 'card.updated']
  for (const kname of kinds) es.addEventListener(kname, (m: MessageEvent) => { try { onEvent({ event: kname, data: JSON.parse(m.data) }) } catch { /* ignore */ } })
  es.onmessage = (m) => { try { const d = JSON.parse(m.data); onEvent({ event: d.event || 'message', data: d.data || d }) } catch { /* ignore */ } }
  return () => es.close()
}
/** Fixture replay with the original timing (ts_offset_s), sped up by `speed`. Returns a stop fn. */
export async function playFixture(url: string, onEvent: (e: RawEvent) => void, speed = 1, maxGapS = 2.5): Promise<() => void> {
  const j = await fetch(url).then(r => r.json())
  const evs: RawEvent[] = j.events
  let stopped = false
  ;(async () => {
    let last = 0
    for (const e of evs) {
      if (stopped) return
      const gap = Math.min(Math.max((e.ts_offset_s ?? 0) - last, 0), maxGapS) / speed
      last = e.ts_offset_s ?? last
      if (gap > 0) await new Promise(r => setTimeout(r, gap * 1000))
      if (stopped) return
      onEvent(e)
    }
  })()
  return () => { stopped = true }
}
