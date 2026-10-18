import type { GraphNode, RawEvent, RunState } from './types'

export const emptyRun = (): RunState => ({
  run_id: '', question: '', source: 'web', company_id: '', nodes: {}, order: [], decisions: {}, turns: [], status: 'idle', startedAt: Date.now(),
})

const TOOL_LABEL: Record<string, string> = {
  context: 'read books', scoring: 'score invoices', forecast: 'forecast cash', levers: 'find levers', answer: 'answer', action: 'act',
}
const LIVE_CALL_PLACEHOLDER = 'Live phone call'

export function reduce(run: RunState, ev: RawEvent, now = Date.now()): RunState {
  const d = ev.data || {}
  switch (ev.event) {
    case 'run.start':
      return { ...emptyRun(), run_id: d.run_id || ev.run_id || '', parent_run_id: d.parent_run_id, question: d.question || '', source: d.source || 'web', company_id: d.company_id || '', status: 'open', startedAt: now,
        turns: d.question && d.question !== LIVE_CALL_PLACEHOLDER
          ? [{ kind: 'you', text: d.question, at: now }]
          : [] }
    case 'node.create': {
      const n: GraphNode = { node_id: d.node_id, type: d.type, title: d.title, status: d.status || 'running', parent: d.parent ?? null, parent_run_id: d.parent_run_id, data: d.data || {}, rows: d.data?.rows || [], rounds: [], createdAt: now, doneAt: d.status === 'done' ? now : undefined }
      const turns = run.turns.slice()
      if (n.type !== 'answer' && n.type !== 'action') turns.push({ kind: 'tool', text: TOOL_LABEL[n.type] || n.type, meta: n.title, at: now })
      if (n.type === 'action') turns.push({ kind: 'tool', text: n.title, meta: d.data?.kind, at: now })
      return { ...run, nodes: { ...run.nodes, [n.node_id]: n }, order: [...run.order, n.node_id], turns }
    }
    case 'node.update': {
      const prev = run.nodes[d.node_id]; if (!prev) return run
      const n: GraphNode = { ...prev, data: { ...prev.data, ...(d.data || {}) }, rows: prev.rows.slice(), rounds: prev.rounds.slice() }
      if (n.type === 'forecast' && d.data?.cash_at_target != null && n.data.initial_cash_at_target == null) { n.data.initial_cash_at_target = d.data.cash_at_target; n.data.initial_need = d.data.need }
      if (d.status) { n.status = d.status; if (d.status === 'done') n.doneAt = now }
      if (d.progress) n.progress = d.progress
      if (Array.isArray(d.data?.rows)) n.rows = d.data.rows
      if (d.row) n.rows.push(d.row)
      if (d.data?.round) n.rounds.push(d.data.round)
      let turns = run.turns
      if (d.status === 'done') {
        turns = run.turns.map(t => (t.kind === 'tool' && t.meta === prev.title && t.secs == null) ? { ...t, secs: (now - prev.createdAt) / 1000, meta: summarize(n) } : t)
      }
      return { ...run, nodes: { ...run.nodes, [n.node_id]: n }, turns }
    }
    case 'decision':
      return { ...run, decisions: { ...run.decisions, [d.decision_id]: { decision_id: d.decision_id, node_id: d.node_id, prompt: d.prompt, options: d.options || [], auto_resolves_in_s: d.auto_resolves_in_s ?? null, default: d.default } } }
    case 'decision.resolved': {
      const dec = run.decisions[d.decision_id]; if (!dec) return run
      return { ...run, decisions: { ...run.decisions, [d.decision_id]: { ...dec, resolved: d.option_id || d.resolved } } }
    }
    case 'speech': {
      if (d.kind === 'caller' || d.speaker === 'caller') {
        const text = String(d.text || '').trim()
        if (!text) return run
        return {
          ...run,
          question: !run.question || run.question === LIVE_CALL_PLACEHOLDER ? text.slice(0, 4000) : run.question,
          turns: [...run.turns, { kind: 'you', text, at: now }],
        }
      }
      return { ...run, turns: [...run.turns, { kind: 'owed', text: plain(String(d.text || '')).split(/(?<=[.!?])\s/).slice(0, 3).join(' '), at: now }] }
    }
    case 'report.ready':
      return { ...run, report_id: d.report_id }
    case 'run.end':
      return { ...run, status: d.status === 'closed' ? 'closed' : 'open' }
    default:
      return run
  }
}

function summarize(n: GraphNode): string {
  const x = n.data
  switch (n.type) {
    case 'context': return `bank $${k(x.bank_balance)}, payroll $${k(x.payroll_due_by_target ?? x.payroll_amount)}, bills $${k(x.bills_due_by_target)}`
    case 'scoring': return `${n.rows.length || n.progress?.total || ''} scored`
    case 'forecast': return `cushion $${Math.round(x.cash_at_target ?? -(x.gap ?? 0)).toLocaleString()}`
    case 'levers': return (x.levers || []).map((l: any) => l.label).join(', ')
    default: return n.title
  }
}
export const plain = (t: string) => (t || '').replace(/[#*_`>]+/g, '').replace(/\n{2,}/g, ' ').replace(/\s+/g, ' ').trim()
export const k = (v?: number) => v == null ? '—' : (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : Math.round(v).toString())
export const money = (v?: number) => v == null ? '—' : '$' + Math.round(v).toLocaleString()

/** Action nodes that are part of a customer conversation. "No actions taken" and owner follow-ups are status, not messages. */
export const CONVERSATION_KINDS = new Set(['reminder', 'reply', 'negotiation', 'payment'])
export const conversationActions = (nodes: GraphNode[]) => nodes.filter(n => n.type === 'action' && CONVERSATION_KINDS.has(String(n.data?.kind)))

/** Milliseconds to hold before the next event so a live run unfolds step by step. A backlog (page load of a long chat,
 *  a burst from the server) is shown at once: pacing a history makes clicks look dead. */
export const presentationBeat = (event: string, queued: number) =>
  queued > 3 ? 0 : event === 'node.create' ? 420 : event === 'decision' ? 250 : event === 'speech' ? 150 : 0
