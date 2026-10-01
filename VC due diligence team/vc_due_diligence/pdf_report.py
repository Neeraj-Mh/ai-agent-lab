"""Consulting-style (BCG / McKinsey) 4-page executive PDF built with reportlab.

Pure function - no ADK dependency - so it can be called by the agent tool or
rebuilt later from a saved run folder with `python make_pdf.py outputs/<run>`.

Page plan (each page has an "action title" - the one-sentence so-what):
  1. Executive summary    - verdict banner, KPI tiles, Situation/Complication/Resolution, key takeaways
  2. Company & market     - fact sheet, market sizing tiles, competitor table, market insights
  3. Financial outlook    - bear/base/bull chart, highlights, unit economics
  4. Risks & next steps   - risk chart, top-risk table, next steps, disclaimer
"""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, String
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepInFrame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B1F3A")
TEAL = colors.HexColor("#0F766E")
INK = colors.HexColor("#1E293B")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
TINT = colors.HexColor("#F1F5F9")
TEAL_TINT = colors.HexColor("#F0FDFA")
VERDICT_COLORS = {
    "STRONG INVEST": colors.HexColor("#15803D"),
    "INVEST": colors.HexColor("#15803D"),
    "WATCH": colors.HexColor("#B45309"),
    "PASS": colors.HexColor("#B91C1C"),
}

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 14 * mm
FOOTER_H = 10 * mm
FRAME_H = PAGE_H - 2 * MARGIN - HEADER_H - FOOTER_H

# ----------------------------------------------------------------------------- text helpers
_REPLACE = {"₹": "INR ", "€": "EUR ", "£": "GBP ", "≈": "~", "→": "->", "≥": ">=", "≤": "<=", "×": "x", "✓": "-"}


def clean(text) -> str:
    """Make text safe for built-in PDF fonts (cp1252) and reportlab's mini-XML."""
    s = str(text or "")
    for k, v in _REPLACE.items():
        s = s.replace(k, v)
    s = s.encode("cp1252", "ignore").decode("cp1252")
    s = s.replace("**", "")  # strip markdown bold markers
    return escape(s.strip())


def split_kv(item: str):
    label, sep, value = str(item).partition(":")
    return (label.strip(), value.strip()) if sep else ("", label.strip())


def split_cols(item: str, n: int):
    parts = [p.strip() for p in str(item).split("|")]
    return (parts + [""] * n)[:n]


S = {
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=8, textColor=TEAL, leading=10,
                             spaceAfter=2),
    "action": ParagraphStyle("action", fontName="Helvetica-Bold", fontSize=15.5, textColor=NAVY, leading=19.5,
                             spaceAfter=8),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9, textColor=TEAL, leading=11, spaceBefore=6,
                        spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, textColor=INK, leading=12.5),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9, textColor=INK, leading=12.5,
                             leftIndent=10, bulletIndent=0, spaceAfter=3),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7, textColor=MUTED, leading=9),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, textColor=INK, leading=10.5),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=10.5),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
    "tile_k": ParagraphStyle("tile_k", fontName="Helvetica-Bold", fontSize=6.8, textColor=MUTED, leading=8.5),
    "tile_v": ParagraphStyle("tile_v", fontName="Helvetica-Bold", fontSize=13, textColor=NAVY, leading=16),
    "verdict": ParagraphStyle("verdict", fontName="Helvetica-Bold", fontSize=13, textColor=colors.white,
                              leading=16, alignment=TA_CENTER),
    "verdict_sub": ParagraphStyle("verdict_sub", fontName="Helvetica", fontSize=8.5, textColor=colors.white,
                                  leading=11, alignment=TA_CENTER),
    "scr_h": ParagraphStyle("scr_h", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
}


def P(text, style="body"):
    return Paragraph(clean(text), S[style])


def bullets(items, limit=6, max_chars=220):
    return [Paragraph(clean(str(i)[:max_chars]), S["bullet"], bulletText="•") for i in (items or [])[:limit]]


def section(title):
    return P(title.upper(), "h")


def table(rows, col_widths, header=True, zebra=True):
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), TINT))
    t.setStyle(TableStyle(style))
    return t


def tiles(items, cols=3, width=CONTENT_W, limit=6):
    """KPI tiles from 'Label: Value' strings."""
    items = list(items or [])[:limit]
    if not items:
        return Spacer(1, 1)
    cells = []
    for it in items:
        label, value = split_kv(it)
        cells.append([P(label.upper() or "METRIC", "tile_k"), P(value or label, "tile_v")])
    while len(cells) % cols:
        cells.append("")
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    gap = 4
    w = (width - gap * (cols - 1)) / cols
    t = Table(rows, colWidths=[w] * cols, rowHeights=None)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TINT),
        ("LINEBEFORE", (0, 0), (-1, -1), 2.5, TEAL),
        ("LINEAFTER", (0, 0), (-1, -1), gap, colors.white),
        ("LINEBELOW", (0, 0), (-1, -1), gap, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def image(path, max_w, max_h):
    if not path or not Path(path).exists():
        return P("(chart not available)", "small")
    iw, ih = ImageReader(str(path)).getSize()
    scale = min(max_w / iw, max_h / ih)
    return Image(str(path), width=iw * scale, height=ih * scale)


def fit(flowables):
    """Guarantee a section stays on one page by shrinking it if necessary."""
    return KeepInFrame(CONTENT_W, FRAME_H - 4, flowables, mode="shrink")



_UNITS = {"K": 1e3, "M": 1e6, "MN": 1e6, "B": 1e9, "BN": 1e9, "T": 1e12, "TN": 1e12, "CR": 1e7, "L": 1e5}


def parse_amount(text: str):
    """'$18B (global)' -> 1.8e10 ; returns None if no number found."""
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(TN|BN|MN|CR|[KMBTL])?\b", str(text).upper().replace(",", ""))
    if not m:
        return None
    return float(m.group(1)) * _UNITS.get(m.group(2) or "", 1)


def market_circles(items, size=62 * mm):
    """Consulting-style nested TAM / SAM / SOM circles (area-proportional where numbers parse)."""
    items = list(items or [])[:3]
    d = Drawing(size, size)
    if not items:
        return d
    vals = [parse_amount(split_kv(i)[1] or i) for i in items]
    if all(v and v > 0 for v in vals) and vals == sorted(vals, reverse=True):
        radii = [size / 2 * math.sqrt(v / vals[0]) for v in vals]
        radii = [max(r, size * 0.11) for r in radii]  # keep tiny SOMs visible
    else:
        radii = [size / 2 * f for f in (1.0, 0.66, 0.36)][: len(items)]
    fills = [colors.HexColor("#DBEAFE"), colors.HexColor("#93C5FD"), NAVY]
    for i, (item, r) in enumerate(zip(items, radii)):
        cx, cy = size / 2, r  # circles share a bottom tangent
        d.add(Circle(cx, cy, r, fillColor=fills[i], strokeColor=colors.white, strokeWidth=1))
        label = split_kv(item)[0] or ["TAM", "SAM", "SOM"][i]
        y = cy + r - 10 if i < len(items) - 1 else cy - 2.5
        d.add(String(cx, y, clean(label.upper())[:6], fontName="Helvetica-Bold", fontSize=7,
                     fillColor=colors.white if i == 2 else NAVY, textAnchor="middle"))
    return d


RATING_COLORS = {"HIGH": colors.HexColor("#15803D"), "MEDIUM": colors.HexColor("#B45309"),
                 "MED": colors.HexColor("#B45309"), "LOW": colors.HexColor("#B91C1C")}


# ----------------------------------------------------------------------------- page chrome
def _chrome(canvas, doc, brief, page_titles):
    canvas.saveState()
    page = canvas.getPageNumber()
    # header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - MARGIN - HEADER_H + 4 * mm, PAGE_W, HEADER_H + MARGIN - 4 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#7DD3FC"))
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(MARGIN, PAGE_H - MARGIN + 1 * mm, "INVESTMENT COMMITTEE  |  EXECUTIVE BRIEF")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(MARGIN, PAGE_H - MARGIN - 5 * mm, clean(brief.get("company_name", "")).replace("&amp;", "&"))
    canvas.setFont("Helvetica", 8)
    title = page_titles[page - 1] if page - 1 < len(page_titles) else ""
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN - 5 * mm, f"{page}. {title}")
    # footer
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, MARGIN + FOOTER_H - 3 * mm, PAGE_W - MARGIN, MARGIN + FOOTER_H - 3 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.8)
    canvas.drawString(
        MARGIN, MARGIN + 2 * mm,
        f"Confidential | {brief.get('date', '')} | AI-generated analysis - verify with primary sources. Not investment advice.")
    canvas.drawRightString(PAGE_W - MARGIN, MARGIN + 2 * mm, f"Page {page}")
    canvas.restoreState()


# ----------------------------------------------------------------------------- pages
def _page1(b):
    rec = (b.get("recommendation") or "WATCH").upper()
    vcolor = VERDICT_COLORS.get(rec, TEAL)
    verdict = Table(
        [[P(f"RECOMMENDATION: {rec}", "verdict")],
         [P(f"Conviction: {b.get('conviction', '-')}   |   Valuation view: {b.get('proposed_valuation', '-')}",
            "verdict_sub")]],
        colWidths=[CONTENT_W])
    verdict.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), vcolor),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    scr_w = (CONTENT_W - 8) / 3
    scr = Table(
        [[P("SITUATION", "scr_h"), P("COMPLICATION", "scr_h"), P("RESOLUTION", "scr_h")],
         [P(b.get("situation", ""), "cell"), P(b.get("complication", ""), "cell"), P(b.get("resolution", ""), "cell")]],
        colWidths=[scr_w] * 3)
    scr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), NAVY), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#B45309")),
        ("BACKGROUND", (2, 0), (2, 0), TEAL), ("BACKGROUND", (0, 1), (-1, 1), TINT),
        ("LINEAFTER", (0, 0), (1, -1), 4, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    takeaways = Table([[bullets(b.get("key_takeaways"), limit=5, max_chars=260)]], colWidths=[CONTENT_W])
    takeaways.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL_TINT),
                                   ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
                                   ("TOPPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    return fit([
        P("EXECUTIVE SUMMARY", "kicker"),
        P(b.get("headline", ""), "action"),
        verdict, Spacer(1, 8),
        tiles(b.get("key_metrics"), cols=3), Spacer(1, 8),
        scr, Spacer(1, 4),
        section("Key takeaways"), takeaways,
        *_thesis_and_returns(b),
    ])


def _thesis_and_returns(b):
    out = []
    pillars = [split_cols(p, 2) for p in (b.get("investment_thesis") or [])[:4]]
    if pillars:
        w = (CONTENT_W - 6 * (len(pillars) - 1)) / len(pillars)
        cells = [[P(f"{i + 1}. {t}", "cellb"), Spacer(1, 3), P(e, "cell")] for i, (t, e) in enumerate(pillars)]
        t = Table([cells], colWidths=[w] * len(pillars))
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEABOVE", (0, 0), (-1, 0), 3, NAVY),
                               ("LINEAFTER", (0, 0), (-2, -1), 6, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        out += [section("Investment thesis"), t]
    scen = (b.get("return_scenarios") or [])[:3]
    if scen:
        rows = [[P(h, "th") for h in ("Scenario", "Exit value", "MOIC", "Key assumption")]]
        rows += [[P(c[0], "cellb"), P(c[1], "cell"), P(c[2], "cellb"), P(c[3], "cell")]
                 for c in (split_cols(x, 4) for x in scen)]
        out += [section("Return scenarios"),
                table(rows, [CONTENT_W * 0.14, CONTENT_W * 0.18, CONTENT_W * 0.12, CONTENT_W * 0.56])]
    return out


def _page2(b):
    half = (CONTENT_W - 10) / 2
    facts = [[P(k or "-", "cellb"), P(v, "cell")] for k, v in map(split_kv, (b.get("company_facts") or [])[:9])]
    fact_tbl = table(facts or [[P("-", "cell"), P("Not available", "cell")]], [half * 0.38, half * 0.62],
                     header=False)
    legend = []
    for item in (b.get("market_sizing") or [])[:3]:
        label, value = split_kv(item)
        main, _, basis = value.partition("(")
        legend += [P(f"{label.upper()}  {main.strip()}", "tile_v"), P(basis.rstrip(")"), "small"), Spacer(1, 5)]
    sizing_tiles = legend or [P("Not available", "small")]
    sizing = Table([[market_circles(b.get("market_sizing"), size=half * 0.48), sizing_tiles]],
                   colWidths=[half * 0.5, half * 0.5])
    sizing.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    top = Table([[[section("Company fact sheet"), fact_tbl], [section("Market sizing"), sizing]]],
                colWidths=[half + 10, half])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 10)]))

    comp_rows = [[P("Competitor", "th"), P("Scale / positioning", "th"), P("How the target differs", "th")]]
    for item in (b.get("competitors") or [])[:6]:
        c = split_cols(item, 3)
        comp_rows.append([P(c[0], "cellb"), P(c[1], "cell"), P(c[2], "cell")])
    return fit([
        P("COMPANY & MARKET", "kicker"),
        P(b.get("market_headline", ""), "action"),
        top, Spacer(1, 6),
        section("Competitive landscape"),
        table(comp_rows, [CONTENT_W * 0.22, CONTENT_W * 0.36, CONTENT_W * 0.42]),
        *_moat(b),
        section("Market insights"),
        *bullets(b.get("market_insights"), limit=5),
    ])


def _moat(b):
    items = [split_cols(m, 3) for m in (b.get("moat_assessment") or [])[:6]]
    if not items:
        return []
    rows = [[P(h, "th") for h in ("Moat dimension", "Strength", "Evidence")]]
    style_extra = []
    for r, (dim, rating, ev) in enumerate(items, start=1):
        rows.append([P(dim, "cellb"), P(rating.upper(), "th"), P(ev, "cell")])
        style_extra.append(("BACKGROUND", (1, r), (1, r), RATING_COLORS.get(rating.strip().upper(), MUTED)))
    t = table(rows, [CONTENT_W * 0.24, CONTENT_W * 0.12, CONTENT_W * 0.64], zebra=False)
    t.setStyle(TableStyle(style_extra))
    return [section("Moat scorecard"), t]


def _page3(b, images):
    half = (CONTENT_W - 10) / 2
    ue = [[P("Metric", "th"), P("Value / estimate", "th")]] + [
        [P(k or "-", "cellb"), P(v, "cell")] for k, v in map(split_kv, (b.get("unit_economics") or [])[:8])]
    bottom = Table([[[section("Financial highlights"), *bullets(b.get("financial_highlights"), limit=5)],
                     [section("Unit economics"), table(ue, [half * 0.5, half * 0.5])]]],
                   colWidths=[half + 10, half])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (0, 0), 10)]))
    return fit([
        P("FINANCIAL OUTLOOK", "kicker"),
        P(b.get("financial_headline", ""), "action"),
        image(images.get("chart"), CONTENT_W, 92 * mm),
        Spacer(1, 4),
        bottom,
    ])


def _page4(b, images):
    rows = [[P("Category", "th"), P("Key risk", "th"), P("Mitigation / diligence ask", "th")]]
    for item in (b.get("top_risks") or [])[:6]:
        c = split_cols(item, 3)
        rows.append([P(c[0], "cellb"), P(c[1], "cell"), P(c[2], "cell")])

    steps = Table([[[section("Recommended next steps"), *bullets(b.get("next_steps"), limit=6)]]],
                  colWidths=[CONTENT_W])
    steps.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL_TINT),
                               ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return fit([
        P("RISKS & NEXT STEPS", "kicker"),
        P(b.get("risk_headline", ""), "action"),
        image(images.get("risk_chart"), CONTENT_W * 0.8, 62 * mm),
        Spacer(1, 4),
        table(rows, [CONTENT_W * 0.17, CONTENT_W * 0.43, CONTENT_W * 0.40]),
        Spacer(1, 8),
        steps,
        Spacer(1, 6),
        P("Methodology: live web research, top-down and bottom-up market sizing, scenario revenue modelling and a "
          "five-category risk scorecard, produced by the AI VC Due Diligence Agent Team. Figures marked as "
          "estimates are model-derived. Validate with management data, references and primary sources before "
          "any investment decision.", "small"),
    ])


# ----------------------------------------------------------------------------- entry point
PAGE_TITLES = ["Executive summary", "Company & market", "Financial outlook", "Risks & next steps"]


def build_executive_pdf(out_path, brief: dict, images: dict | None = None) -> str:
    """Render the 4-page executive PDF. `images` may contain 'chart' and 'risk_chart' PNG paths."""
    images = images or {}
    brief = dict(brief)
    brief.setdefault("date", dt.date.today().strftime("%d %b %Y"))

    doc = BaseDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN + HEADER_H, bottomMargin=MARGIN + FOOTER_H,
        title=f"{brief.get('company_name', 'Startup')} - Executive Due Diligence Brief",
        author="AI VC Due Diligence Agent Team",
    )
    frame = Frame(MARGIN, MARGIN + FOOTER_H, CONTENT_W, FRAME_H, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame],
                                       onPage=lambda c, d: _chrome(c, d, brief, PAGE_TITLES))])
    story = [
        NextPageTemplate("page"),
        _page1(brief), PageBreak(),
        _page2(brief), PageBreak(),
        _page3(brief, images), PageBreak(),
        _page4(brief, images),
    ]
    doc.build(story)
    return str(out_path)
