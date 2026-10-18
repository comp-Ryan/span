"""One-page Letter PDF of a report dict, with the workflow SVG embedded as vector graphics."""
from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

INK, MUTED, RULE, ACCENT, PAPER = (colors.HexColor(c) for c in ("#1f1d1a", "#6b665e", "#e4ded4", "#ff7a45", "#faf8f4"))
MARGIN = 40


def _s(name, **kw) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 9.5, "leading": 13.5, "textColor": INK}
    return ParagraphStyle(name, **{**base, **kw})


BRAND = _s("brand", fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT)
META = _s("meta", fontSize=8.5, textColor=MUTED, alignment=TA_RIGHT)
QUESTION = _s("q", fontSize=11, textColor=MUTED, leading=15)
ANSWER = _s("a", fontName="Times-Bold", fontSize=21, leading=25)
H = _s("h", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=11, spaceBefore=10, spaceAfter=4)
BODY = _s("body")
ITEM = _s("item", leftIndent=10, bulletIndent=0)
LABEL = _s("label", fontSize=7.5, textColor=MUTED, leading=10)
VALUE = _s("value", fontName="Helvetica-Bold", fontSize=12, leading=15)
VALUE_NOW = _s("value_now", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=ACCENT)
FINE = _s("fine", fontSize=7.5, textColor=MUTED, leading=10)


def _money(x) -> str:
    return "\u2014" if x is None else f"${x:,.2f}"


def _workflow(svg: str, max_w: float, max_h: float):
    d = svg2rlg(io.BytesIO(svg.encode()))
    k = min(max_w / d.width, max_h / d.height, 1.0)
    d.width, d.height = d.width * k, d.height * k
    d.scale(k, k)
    return d


def markdown_paragraphs(text: str) -> list[dict]:
    """Planner narratives are light markdown; turn them into reportlab-safe blocks (heading, bullet, text, table)."""
    blocks, para = [], []
    table = None

    def flush():
        if para:
            blocks.append({"kind": "text", "text": _inline(" ".join(para))})
            para.clear()

    def _inline(raw):
        out = escape(raw.replace("`", ""))
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)

    for line in (text or "").splitlines():
        stripped = line.strip()
        if len(stripped) > 2 and stripped.startswith("|") and stripped.endswith("|"):  # pipe table row
            flush()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue  # the |---|---| line under the header
            cells = [_inline(c) for c in cells]
            if table is None:
                table = {"kind": "table", "header": cells, "rows": []}
                blocks.append(table)
            else:
                table["rows"].append(cells)
            continue
        table = None
        if not stripped:
            flush()
        elif re.match(r"^#{1,6}\s+", stripped):
            flush()
            blocks.append({"kind": "heading", "text": _inline(re.sub(r"^#{1,6}\s+", "", stripped))})
        elif re.match(r"^[-*\u2022]\s+", stripped):
            flush()
            blocks.append({"kind": "bullet", "text": _inline(re.sub(r"^[-*\u2022]\s+", "", stripped))})
        else:
            para.append(stripped)
    flush()
    return blocks


def render_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=MARGIN, title=f"Span report \u2014 {report.get('company', '')}",
                            author="Span")
    fw, fh = doc.width, doc.height
    try:
        when = datetime.fromisoformat(report["generated_at"]).astimezone(UTC).strftime("%b %d, %Y %H:%M UTC")
    except (KeyError, TypeError, ValueError):
        when = report.get("generated_at", "")

    head = Table([[Paragraph("OWED", BRAND), Paragraph(f"{escape(report['company'])}<br/>{when}", META)]],
                 colWidths=[fw / 2, fw / 2])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))

    n = report["numbers"]
    if any(n.get(k) is not None for k in ("bank_balance", "payroll", "owed", "expected_by_target", "gap_then", "gap_now")):
        stats = [("Bank balance", _money(n.get("bank_balance"))), ("Payroll", _money(n.get("payroll"))), ("Customers owe", _money(n.get("owed"))),
                 ("Expected in time", _money(n.get("expected_by_target"))), ("Gap when asked", _money(n.get("gap_then"))),
                 ("Gap now", _money(n.get("gap_now")))]
    elif n.get("overdue") is not None:  # ranking-only answer: what it ranked
        stats = [("Overdue, ranked", _money(n.get("overdue"))), ("Open balance, ranked", _money(n.get("open_balance"))),
                 ("Customers ranked", str(n.get("customers_ranked") or 0)), ("Considered", str(n.get("customers_considered") or "\u2014"))]
    else:
        stats = [("Numbers", "This answer did not need a cash forecast.")]
    numbers = Table([[Paragraph(label.upper(), LABEL) for label, _ in stats],
                     [Paragraph(value, VALUE_NOW if i == len(stats) - 1 and len(stats) > 1 else VALUE)
                      for i, (_, value) in enumerate(stats)]], colWidths=[fw / len(stats)] * len(stats))
    numbers.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                 ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                                 ("LINEBEFORE", (1, 0), (-1, -1), 0.6, RULE)]))

    left_w = fw * 0.46
    left = [Paragraph("WHAT I DID", H)]
    left += [Paragraph(f"<b>{escape(a['title'])}</b> \u2014 {escape(a['result'])}", ITEM, bulletText="\u2022")
             for a in report["actions"]] or [Paragraph("Nothing yet." if any(x.get("type") == "levers" for x in report["workflow"]["nodes"])
                                                       else "No actions were needed for this question.", BODY)]
    left.append(Paragraph("STILL OPEN", H))
    left += [Paragraph(escape(i), ITEM, bulletText="\u2022") for i in report["open_items"]] or \
        [Paragraph("Nothing open.", BODY)]
    left.append(Paragraph("SUMMARY", H))
    for block in markdown_paragraphs(report["narrative"]):
        if block["kind"] == "heading":
            left.append(Paragraph(f"<b>{block['text']}</b>", _s("nh", spaceBefore=4, spaceAfter=2)))
        elif block["kind"] == "bullet":
            left.append(Paragraph(block["text"], ITEM, bulletText="\u2022"))
        elif block["kind"] == "table":
            ncols = max([len(block["header"])] + [len(r) for r in block["rows"]]) or 1
            pad = lambda cells: cells + [""] * (ncols - len(cells))
            data = [[Paragraph(f"<b>{c}</b>", FINE) for c in pad(block["header"])]]
            data += [[Paragraph(c, FINE) for c in pad(row)] for row in block["rows"]]
            grid = Table(data, colWidths=[left_w / ncols] * ncols)
            grid.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE), ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                                      ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                      ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            left.append(grid)
        else:
            left.append(Paragraph(block["text"], _s("np", spaceAfter=6)))

    right_w = fw - left_w - 18
    body_h = fh - 190
    right = [Paragraph("HOW I GOT THERE", H), _workflow(report["workflow"]["svg"], right_w, body_h - 30)]
    cols = Table([[KeepInFrame(left_w, body_h, left, mode="shrink"), right]], colWidths=[left_w + 18, right_w])
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (0, 0), 18), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))

    story = [head, Spacer(1, 14), Paragraph(escape(report["question"]), QUESTION), Spacer(1, 4),
             Paragraph(escape(report["answer"]), ANSWER), Spacer(1, 14), numbers, Spacer(1, 4), cols,
             Spacer(1, 10), Paragraph(" \u00b7 ".join(escape(d) for d in report["disclosures"]), FINE)]
    doc.build([KeepInFrame(fw, fh, story, mode="shrink")])
    return buf.getvalue()
