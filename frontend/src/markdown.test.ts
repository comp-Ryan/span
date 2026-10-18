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
