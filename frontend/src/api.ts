import type { HistoryPoint } from './forecastTrend'
import type { Brief, CashProjection, Company, CustomerDetail, CustomerRow, Health, HeatmapResponse, PaymentsResponse, RawEvent, ReportDoc, ReportsResponse, RunSummary } from './types'

const BASE = '/api'

export async function startRun(company: string, question: string, source = 'web', parentRunId?: string) {
  const r = await fetch(`${BASE}/ask?company=${encodeURIComponent(company)}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question, source, parent_run_id: parentRunId }) })
  if (!r.ok) throw new Error((await r.json()).error?.message || 'Request failed')
  return r.json() as Promise<{ run_id: string; intent: string }>
}
export async function resolveDecision(decisionId: string, optionId: string, company: string, selected?: string[]) {
  const r = await fetch(`${BASE}/decisions/${decisionId}?company=${encodeURIComponent(company)}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ option_id: optionId, note: selected ? JSON.stringify({ selected_customers: selected }) : undefined, selected_customers: selected }) })
  if (!r.ok) throw new Error((await r.json()).error?.message || 'Request failed')
  return r.json()
}
export async function replay(runId: string, company?: string): Promise<RawEvent[]> {
  const r = await fetch(`${BASE}/runs/${runId}?company=${encodeURIComponent(company || "company-020")}`); if (!r.ok) throw new Error('Could not replay this thread'); const j = await r.json(); return j.events || []
}
export async function getReport(id: string, company = 'company-020'): Promise<ReportDoc> {
  const r = await fetch(`${BASE}/reports/${encodeURIComponent(id)}?company=${encodeURIComponent(company)}`)
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}
async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error?.message || `${r.status} ${r.statusText}`)
  return r.json()
}
export const getCompanies = () => getJson<{ companies: Company[] }>('/companies').then(j => j.companies)
export const getBrief = (company: string) => getJson<Brief>(`/brief?company=${encodeURIComponent(company)}`)
export const getRuns = (company: string) => getJson<{ runs: RunSummary[] }>(`/runs?company=${encodeURIComponent(company)}`).then(j => j.runs)
export const getCash = (company: string, target: string) => getJson<CashProjection>(`/cash?${new URLSearchParams({ company, target })}`)
export const getCashHistory = (company: string, limit = 30) => getJson<{ storage: string; points: HistoryPoint[] }>(`/cash/history?${new URLSearchParams({ company, limit: String(limit) })}`)
export const getPayments = (company: string) => getJson<PaymentsResponse>(`/payments?company=${encodeURIComponent(company)}`)
export const getReports = (company: string) => getJson<ReportsResponse>(`/reports?company=${encodeURIComponent(company)}`)
export const getCustomers = (company: string) => getJson<{ customers: CustomerRow[] }>(`/customers?company=${encodeURIComponent(company)}`).then(j => j.customers)
export const getCustomer = (id: string, company: string) => getJson<CustomerDetail>(`/customers/${encodeURIComponent(id)}?company=${encodeURIComponent(company)}`)
export const getHeatmap = (company: string) => getJson<HeatmapResponse>(`/customers/heatmap?company=${encodeURIComponent(company)}`)
export const getHealth = () => getJson<Health>('/health')
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

export async function generateReport(runId: string, company: string): Promise<{ report_id: string } | null> {
  const r = await fetch(`${BASE}/reports/generate?run_id=${encodeURIComponent(runId)}&company=${encodeURIComponent(company)}`, { method: 'POST' })
  if (!r.ok) return null
  return r.json()
}
