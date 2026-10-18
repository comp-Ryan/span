"""DB-free: planner narratives are markdown; the PDF and the page must render headings, bullets and bold."""
from owed.reports.pdf import markdown_paragraphs

DETAIL = ("### Why\nA chase ranking was run.\n\n### Numbers used\n- **Total recoverable amount**: $1,023.51\n"
          "- **Eastgate Cyclery & Co.** (Invoice `inv-03288`): $347.43 (7 days overdue)\n\n"
          "### What I'd do next\n- Await owner approval for decision `d-a0c6`.\n- **Uncertainties**: exact dates cannot be guaranteed.")


def test_markdown_paragraphs_turns_headings_bullets_and_bold_into_reportlab_markup():
    blocks = markdown_paragraphs(DETAIL)
    kinds = [b['kind'] for b in blocks]
    assert kinds == ['heading', 'text', 'heading', 'bullet', 'bullet', 'heading', 'bullet', 'bullet']
    assert blocks[0]['text'] == 'Why'
    assert blocks[3]['text'] == '<b>Total recoverable amount</b>: $1,023.51'
    assert blocks[4]['text'] == '<b>Eastgate Cyclery &amp; Co.</b> (Invoice inv-03288): $347.43 (7 days overdue)'
    assert '`' not in blocks[6]['text'] and '<b>Uncertainties</b>' in blocks[7]['text']


def test_markdown_paragraphs_keeps_plain_paragraphs():
    assert markdown_paragraphs('First paragraph.\n\nSecond <one>.') == [
        {'kind': 'text', 'text': 'First paragraph.'}, {'kind': 'text', 'text': 'Second &lt;one&gt;.'}]
    assert markdown_paragraphs('') == []
