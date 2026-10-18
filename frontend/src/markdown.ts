/** Light markdown from the planner's written detail: headings, bullets, paragraphs, **bold**; backticks dropped. */
export type Run = { bold: boolean; text: string }
export type Block = { kind: 'heading'; text: string } | { kind: 'paragraph'; runs: Run[] } | { kind: 'list'; items: Run[][] }

export function inlineRuns(text: string): Run[] {
  const clean = text.replace(/`/g, '')
  const runs: Run[] = []
  const re = /\*\*(.+?)\*\*/g
  let last = 0, m: RegExpExecArray | null
  while ((m = re.exec(clean))) {
    if (m.index > last) runs.push({ bold: false, text: clean.slice(last, m.index) })
    runs.push({ bold: true, text: m[1] })
    last = m.index + m[0].length
  }
  if (last < clean.length) runs.push({ bold: false, text: clean.slice(last) })
  return runs
}

export function markdownBlocks(text: string): Block[] {
  const blocks: Block[] = []
  let para: string[] = []
  const flush = () => { if (para.length) { blocks.push({ kind: 'paragraph', runs: inlineRuns(para.join(' ')) }); para = [] } }
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim()
    if (!line) { flush(); continue }
    const heading = line.match(/^#{1,6}\s+(.*)$/)
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    if (heading) { flush(); blocks.push({ kind: 'heading', text: heading[1].replace(/`/g, '') }); continue }
    if (bullet) {
      flush()
      const last = blocks[blocks.length - 1]
      if (last && last.kind === 'list') last.items.push(inlineRuns(bullet[1]))
      else blocks.push({ kind: 'list', items: [inlineRuns(bullet[1])] })
      continue
    }
    para.push(line)
  }
  flush()
  return blocks
}
