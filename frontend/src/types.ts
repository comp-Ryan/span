export type NodeType = 'context' | 'scoring' | 'forecast' | 'answer' | 'levers' | 'action'
export type NodeStatus = 'running' | 'done' | 'failed' | 'waiting'

export interface ScoreRow {
  invoice_id: string; customer_id?: string; customer: string; amount: number; days_past_due: number
  p_paid_by_target: number; p_never: number; band: 'green' | 'amber' | 'red'; source?: string; expected_days_to_pay?: number | null
}
export interface Lever {
  id: string; label: string; recovers: number
  targets?: { customer_id: string; customer: string; amount: number; n_invoices?: number; days_past_due?: number; p_paid_by_target?: number; reason?: string }[]
  bills?: { bill_id: string; vendor: string; amount: number; due_date: string; vendor_tolerance?: string }[]
}
export interface Decision { decision_id: string; node_id: string; prompt: string; options: { id: string; label: string }[]; auto_resolves_in_s: number | null; default?: string; resolved?: string }
export interface GraphNode {
  node_id: string; type: NodeType; title: string; status: NodeStatus; parent: string | null; parent_run_id?: string
  data: Record<string, any>; rows: ScoreRow[]; progress?: { done: number; total: number }; rounds: any[]
  createdAt: number; doneAt?: number
}
export interface Turn { kind: 'you' | 'owed' | 'tool'; text: string; meta?: string; secs?: number; at: number }
export interface RunState {
  run_id: string; parent_run_id?: string; question: string; source: string; company_id: string
  nodes: Record<string, GraphNode>; order: string[]
  decisions: Record<string, Decision>; turns: Turn[]; status: 'open' | 'closed' | 'idle'; report_id?: string
  startedAt: number
}
export interface RawEvent { event: string; data: any; ts_offset_s?: number; run_id?: string; company_id?: string }

/* GET /reports/{report_id} — see docs/api-contract.md */
export interface ReportNode {
  id: string; type: NodeType; title: string; status: NodeStatus; parent: string | null
  data: Record<string, any>
}
export interface ReportDoc {
  report_id: string; run_id: string; generated_at: string; company: string
  question: string; answer: string
  numbers: {
    bank_balance?: number; payroll?: number; owed?: number
    expected_by_target?: number; bills_due_by_target?: number; gap_then?: number; gap_now?: number
    overdue?: number; open_balance?: number; customers_ranked?: number; customers_considered?: number  // ranking-only runs
  }
  workflow: { nodes: ReportNode[]; edges: { from: string; to: string }[]; svg?: string }
  actions: { title: string; result: string }[]
  open_items: string[]; narrative: string; disclosures: string[]; pdf_url?: string
}

/* ---------- home page (GET /companies, /brief, /runs, /cash) ---------- */
export interface Company { id: string; name: string; profile: string; distressed: boolean; owed_total: number; overdue_total: number }
export interface Brief {
  company: { id: string; name: string; profile: string }; as_of: string; headline: string
  owed_total: number; overdue_total: number; expected_in_30d: number
  benchmark: { dso_days: number; peer_median_dso_days: number; peer_profile: string; peer_count: number } | null
  audio_url: string | null
  bank_balance: number; open_invoices: number
  payroll_next: { date: string; amount: number; headcount: number } | null
  bills_due_week: { total: number; count: number; through: string }
}
export interface RunSummary { run_id: string; question: string; source: string; started_at: string; status: string; answer_title: string | null; report_id: string | null; parent_run_id?: string | null }
export interface CashDay { date: string; inflow: number; outflow: number; balance: number }
export interface CashProjection { start: string; target: string; opening_balance: number; days: CashDay[]; pessimistic_days: CashDay[]; payroll_dates: string[]; low_point: { date: string; balance: number }; pessimistic_low_point: { date: string; balance: number } }

/* ---------- get paid / reports / customers (GET /payments, /reports, /customers) ---------- */
export interface PayLink { pay_token: string; invoice_id: string; doc_number: string | null; customer_id: string; customer_name: string; status: string; created_at: string; run_id: string | null; amount: number; pay_url: string }
export interface Payment { payment_id: string; invoice_id: string; customer_name: string; amount: number; rail: string; reference: string | null; paid_at: string; run_id: string | null }
export interface PaymentsResponse { pay_links: PayLink[]; payments: Payment[]; totals: { links: number; unpaid: number; collected: number; outstanding: number } }
export interface ReportSummary { report_id: string; run_id: string; question: string; answer: string; generated_at: string; pdf_url: string }
export interface UnreportedRun { run_id: string; question: string; answer_title: string | null; started_at: string }
export interface ReportsResponse { reports: ReportSummary[]; unreported: UnreportedRun[] }
export type Reliability = 'green' | 'amber' | 'red' | null
export interface CustomerRow { id: string; display_name: string; open_balance: number; overdue_balance: number; open_invoices: number; avg_days_late: number | null; paid_invoices: number; written_off: number; reliability: Reliability }
export interface CustomerHistoryItem { invoice_id: string; amount: number; due_date: string; days_late: number | null; status: string }
export interface CustomerInvoice { invoice_id: string; doc_number: string | null; open_balance: number; due_date: string; days_past_due: number; p_paid_by_target: number; p_never: number; band: 'green' | 'amber' | 'red' }
export interface CustomerActivity { kind: 'reminder' | 'reply' | 'negotiation' | 'payment'; at: string; title: string; detail: string | null; run_id: string | null }
export interface CustomerDetail {
  customer: CustomerRow & { payment_terms: string | null; payment_terms_days: number | null }
  target_date: string; history: CustomerHistoryItem[]; invoices: CustomerInvoice[]; activity: CustomerActivity[]
}
export type HeatmapStatus = 'paid_on_time' | 'paid_late' | 'very_late' | 'unpaid' | 'overdue' | 'written_off' | 'none'
export interface HeatmapCell {
  month: string; invoices: number; amount: number; status: HeatmapStatus
  paid_on_time: number; paid_late: number; very_late: number; unpaid: number; overdue: number; written_off: number
}
export interface HeatmapCustomer { id: string; display_name: string; open_balance: number; cells: HeatmapCell[] }
export interface HeatmapResponse { months: string[]; customers: HeatmapCustomer[] }
export interface Health { ok: boolean; visa?: string; solana?: string; [k: string]: unknown }
