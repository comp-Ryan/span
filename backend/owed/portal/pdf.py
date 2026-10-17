"""One-page invoice PDF for portal submission (reportlab, same stack as owed.reports.pdf)."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK, MUTED, RULE, ACCENT = (colors.HexColor(c) for c in ("#1f1d1a", "#6b665e", "#e4ded4", "#ff7a45"))
MARGIN = 48


def _s(name, **kw) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 10, "leading": 14, "textColor": INK}
    return ParagraphStyle(name, **{**base, **kw})


BRAND = _s("brand", fontName="Helvetica-Bold", fontSize=18)
TITLE = _s("title", fontName="Helvetica-Bold", fontSize=22, textColor=ACCENT, alignment=TA_RIGHT)
META = _s("meta", fontSize=9, textColor=MUTED, alignment=TA_RIGHT, leading=12)
H = _s("h", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, spaceBefore=12, spaceAfter=3)
BODY = _s("body")
TOTAL = _s("total", fontName="Helvetica-Bold", fontSize=13, alignment=TA_RIGHT)
FINE = _s("fine", fontSize=8, textColor=MUTED, leading=11)


def _money(x) -> str:
    return f"${float(x):,.2f}"


def render_invoice_pdf(invoice: dict) -> bytes:
    """invoice keys: company_name, customer_name, doc_number, amount, due_date, txn_date?, terms?, lines?, memo?"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=MARGIN, title=f"Invoice {invoice['doc_number']}", author=invoice["company_name"])
    w = doc.width
    head = Table([[Paragraph(escape(invoice["company_name"]), BRAND), Paragraph("INVOICE", TITLE)],
                  ["", Paragraph(f"No. {escape(str(invoice['doc_number']))}<br/>Issued {invoice.get('txn_date') or ''}"
                                 f"<br/>Due {invoice['due_date']}", META)]],
                 colWidths=[w * 0.6, w * 0.4])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, 1), 0.75, RULE),
                              ("BOTTOMPADDING", (0, 1), (-1, 1), 10)]))

    lines = invoice.get("lines") or [{"description": invoice.get("memo") or "Services rendered",
                                      "quantity": 1, "unit_price": invoice["amount"], "amount": invoice["amount"]}]
    rows = [["Description", "Qty", "Unit", "Amount"]]
    for ln in lines:
        rows.append([Paragraph(escape(str(ln.get("description") or "")), BODY), f"{float(ln.get('quantity') or 1):g}",
                     _money(ln.get("unit_price") or ln.get("amount") or 0), _money(ln.get("amount") or 0)])
    items = Table(rows, colWidths=[w * 0.55, w * 0.1, w * 0.17, w * 0.18], repeatRows=1)
    items.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    story = [head, Spacer(1, 14),
             Paragraph("BILL TO", H), Paragraph(escape(invoice["customer_name"]), BODY),
             Paragraph("TERMS", H), Paragraph(escape(str(invoice.get("terms") or "Due on receipt")), BODY),
             Spacer(1, 10), items, Spacer(1, 10),
             Paragraph(f"Total due {_money(invoice['amount'])}", TOTAL), Spacer(1, 24),
             Paragraph("Submitted electronically through the customer's accounts-payable portal on behalf of "
                       f"{escape(invoice['company_name'])}. Please reference invoice {escape(str(invoice['doc_number']))} "
                       "on remittance.", FINE)]
    doc.build(story)
    return buf.getvalue()
