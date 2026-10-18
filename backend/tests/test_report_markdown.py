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


def test_markdown_paragraphs_turns_pipe_tables_into_table_blocks():
    from owed.reports.pdf import markdown_paragraphs
    text = '### Numbers used\n| Customer | Overdue | Days late |\n|---|---|---|\n| **Evergreen** | $1,156.20 | 23.0 |\n| Yeoman | $668.58 | 21.1 |\n\nAll have 7-day terms.'
    blocks = markdown_paragraphs(text)
    assert [b['kind'] for b in blocks] == ['heading', 'table', 'text']
    table = blocks[1]
    assert table['header'] == ['Customer', 'Overdue', 'Days late']
    assert table['rows'] == [['<b>Evergreen</b>', '$1,156.20', '23.0'], ['Yeoman', '$668.58', '21.1']]
    assert blocks[2]['text'] == 'All have 7-day terms.'


def test_pdf_renders_a_narrative_table_without_error():
    from owed.reports.pdf import render_pdf
    report = {'report_id': 'rep-t', 'run_id': 'run-t', 'generated_at': '2026-10-18T15:00:00+00:00', 'company': 'Palletbay',
              'question': 'Show me who’s late', 'answer': 'Ten customers are late.',
              'numbers': {'bank_balance': None, 'payroll': None, 'owed': None, 'expected_by_target': None, 'bills_due_by_target': None, 'gap_then': None, 'gap_now': None,
                          'overdue': 6103.13, 'open_balance': 9353.5, 'customers_ranked': 10, 'customers_considered': 56},
              'workflow': {'nodes': [{'id': 'scoring', 'type': 'scoring', 'title': 'Ranked customers', 'status': 'done', 'parent': None, 'data': {}}], 'edges': [], 'svg': '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><rect width="120" height="40" fill="#eee"/></svg>'},
              'actions': [], 'open_items': [], 'disclosures': ['Scoring by Span model'],
              'narrative': '### Numbers used\n| Customer | Overdue |\n|---|---|\n| Evergreen | $1,156.20 |\n| Yeoman | $668.58 |\n'}
    pdf = render_pdf(report)
    assert pdf[:4] == b'%PDF' and len(pdf) > 1500


def test_pdf_text_swaps_glyphs_helvetica_lacks():
    """The planner writes U+2011 (non-breaking hyphen) and U+2212 (minus); the PDF's core fonts have neither."""
    from owed.reports.pdf import markdown_paragraphs, pdf_text
    assert pdf_text('7‑day terms, −15 days') == '7-day terms, -15 days'
    assert pdf_text('<b> & en–dash') == '&lt;b&gt; &amp; en–dash'  # escaped, en dash kept
    assert markdown_paragraphs('All have 7‑day terms.')[0]['text'] == 'All have 7-day terms.'
