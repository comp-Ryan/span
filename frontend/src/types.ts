export type NodeType = 'context' | 'scoring' | 'forecast' | 'answer' | 'levers' | 'action'
export type NodeStatus = 'running' | 'done' | 'failed' | 'waiting'

export interface ScoreRow {
  invoice_id: string; customer: string; amount: number; days_past_due: number
  p_paid_by_target: number; p_never: number; band: 'green' | 'amber' | 'red'; source?: string; expected_days_to_pay?: number
}
export interface Lever {
  id: string; label: string; recovers: number
  targets?: { customer_id: string; customer: string; amount: number; n_invoices?: number; days_past_due?: number; p_paid_by_target?: number; reason?: string }[]
  bills?: { bill_id: string; vendor: string; amount: number; due_date: string; vendor_tolerance?: string }[]
}
export interface Decision { decision_id: string; node_id: string; prompt: string; options: { id: string; label: string }[]; auto_resolves_in_s: number | null; default?: string; resolved?: string }
export interface GraphNode {
  node_id: string; type: NodeType; title: string; status: NodeStatus; parent: string | null
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
    expected_by_target?: number; gap_then?: number; gap_now?: number
  }
  workflow: { nodes: ReportNode[]; edges: { from: string; to: string }[]; svg?: string }
  actions: { title: string; result: string }[]
  open_items: string[]; narrative: string; disclosures: string[]; pdf_url?: string
}
