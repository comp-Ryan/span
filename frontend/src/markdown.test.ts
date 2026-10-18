import { describe, expect, it } from 'vitest'
import { markdownBlocks } from './markdown'

const DETAIL = `### Why
A chase ranking was run on outstanding accounts.

### Numbers used
- **Total recoverable amount**: $1,023.51
- **Eastgate Cyclery & Co.** (Invoice \`inv-03288\`): $347.43

### What I'd do next
- Await owner approval for decision \`d-a0c6\`.`

describe('planner markdown on the report page', () => {
  it('splits headings, paragraphs and bullets, keeping inline bold as runs', () => {
    const blocks = markdownBlocks(DETAIL)
    expect(blocks.map(b => b.kind)).toEqual(['heading', 'paragraph', 'heading', 'list', 'heading', 'list'])
    expect(blocks[0]).toEqual({ kind: 'heading', text: 'Why' })
    expect(blocks[3].kind === 'list' && blocks[3].items[0]).toEqual([{ bold: true, text: 'Total recoverable amount' }, { bold: false, text: ': $1,023.51' }])
    expect(blocks[3].kind === 'list' && blocks[3].items[1].map(r => r.text).join('')).toBe('Eastgate Cyclery & Co. (Invoice inv-03288): $347.43')
  })
  it('treats plain text as paragraphs and ignores blank input', () => {
    expect(markdownBlocks('One.\n\nTwo.')).toEqual([{ kind: 'paragraph', runs: [{ bold: false, text: 'One.' }] }, { kind: 'paragraph', runs: [{ bold: false, text: 'Two.' }] }])
    expect(markdownBlocks('')).toEqual([])
  })
})

describe('tables', () => {
  it('a pipe table becomes a table block with a header row and body rows, bold kept in cells', async () => {
    const { markdownBlocks } = await import('./markdown')
    const text = '### Numbers used\n| Customer | Overdue | Days late |\n|---|---|---|\n| **Evergreen** | $1,156.20 | 23.0 |\n| Yeoman | $668.58 | 21.1 |\n\nAll have 7-day terms.'
    const blocks = markdownBlocks(text)
    expect(blocks.map(b => b.kind)).toEqual(['heading', 'table', 'paragraph'])
    const table = blocks[1] as any
    expect(table.header.map((runs: any[]) => runs.map(r => r.text).join(''))).toEqual(['Customer', 'Overdue', 'Days late'])
    expect(table.rows.length).toBe(2)
    expect(table.rows[0][0]).toEqual([{ bold: true, text: 'Evergreen' }])
    expect(table.rows[1].map((runs: any[]) => runs.map(r => r.text).join(''))).toEqual(['Yeoman', '$668.58', '21.1'])
  })
  it('a table without a separator line is still a table; a lone pipe in prose is not', async () => {
    const { markdownBlocks } = await import('./markdown')
    expect(markdownBlocks('| a | b |\n| 1 | 2 |').map(b => b.kind)).toEqual(['table'])
    expect(markdownBlocks('either this | or that').map(b => b.kind)).toEqual(['paragraph'])
  })
})
