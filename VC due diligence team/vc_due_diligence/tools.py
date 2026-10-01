"""Function tools used by the agent team.

Every tool returns a plain dict so it works identically with Gemini and Claude.
Large inputs (research, memo) are read from session state instead of being
passed as tool arguments, which keeps token usage low.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import os
import re
from pathlib import Path
from typing import Any, Optional

import matplotlib

matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt  # noqa: E402
import markdown as md  # noqa: E402
import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from . import config  # noqa: E402

try:  # ADK injects this; the fallback keeps tools importable in unit tests.
    from google.adk.tools import ToolContext
except Exception:  # pragma: no cover
    ToolContext = Any  # type: ignore

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 VC-DD-Agent/1.0"
)

# Palette (accessible, prints well)
NAVY = "#0B1F3A"
TEAL = "#0F766E"
SLATE = "#475569"
BEAR = "#B91C1C"
BASE = "#1D4ED8"
BULL = "#15803D"


# --------------------------------------------------------------------------- helpers
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "startup").lower()).strip("-")[:40] or "startup"


def _output_dir(tool_context: Optional[ToolContext], company_name: str) -> Path:
    """One folder per run: outputs/<company-slug>_<timestamp>/ (kept in session state)."""
    state = getattr(tool_context, "state", None)
    existing = state.get("output_dir") if state is not None else None
    if existing:
        path = Path(existing)
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = config.OUTPUT_ROOT / f"{_slug(company_name)}_{stamp}"
        if state is not None:
            state["output_dir"] = str(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state(tool_context: Optional[ToolContext], key: str, default: str = "") -> str:
    state = getattr(tool_context, "state", None)
    if state is None:
        return default
    value = state.get(key, default)
    return value if isinstance(value, str) else str(value)


def _img_b64(path: str) -> str:
    if not path or not Path(path).exists():
        return ""
    return base64.b64encode(Path(path).read_bytes()).decode()


# --------------------------------------------------------------------------- 0. intake
def register_startup(company_name: str, website: str, tool_context: ToolContext) -> dict:
    """Register the startup being analysed and create its output folder. Call this once, first.

    Args:
        company_name: Clean company name, e.g. "Razorpay".
        website: Company website URL, or "unknown".
    """
    state = getattr(tool_context, "state", None)
    if state is not None:
        state["company_name"] = company_name
        state["website"] = website
        state["output_dir"] = ""  # force a fresh folder for every new analysis
    out = _output_dir(tool_context, company_name)
    return {"status": "ok", "company_name": company_name, "website": website, "output_dir": str(out)}


# --------------------------------------------------------------------------- 1. URL reader
def fetch_webpage(url: str) -> dict:
    """Fetch a startup's website and return its readable text, title, meta description and key links.

    Args:
        url: Full URL of the page, e.g. https://example.com
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
    except Exception as exc:  # network errors are reported, not raised
        return {"status": "error", "url": url, "error": str(exc)}

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = meta.get("content", "").strip() if meta else ""
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:25]

    keywords = ("about", "team", "pricing", "product", "customers", "careers", "investors", "blog")
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = requests.compat.urljoin(resp.url, a["href"])
        if any(k in (href + text).lower() for k in keywords) and href not in [l["href"] for l in links]:
            links.append({"text": text[:60], "href": href})
        if len(links) >= 15:
            break

    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return {
        "status": "ok",
        "url": resp.url,
        "title": title,
        "meta_description": description,
        "headings": headings,
        "key_links": links,
        "text": text[:8000],
    }


# --------------------------------------------------------------------------- 2. provider-neutral search
def web_search(query: str, max_results: int) -> dict:
    """Search the live web (Tavily if TAVILY_API_KEY is set, otherwise DuckDuckGo).

    Args:
        query: Search query, e.g. "Acme AI series A funding 2026".
        max_results: Number of results to return (1-10).
    """
    max_results = max(1, min(int(max_results or 6), 10))
    backend = config.SEARCH_BACKEND
    try:
        if backend == "tavily":
            r = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": os.environ["TAVILY_API_KEY"],
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                },
                timeout=30,
            )
            r.raise_for_status()
            items = r.json().get("results", [])
            results = [
                {"title": i.get("title"), "url": i.get("url"), "snippet": (i.get("content") or "")[:600]}
                for i in items
            ]
        else:
            try:
                from ddgs import DDGS
            except ImportError:  # older package name
                from duckduckgo_search import DDGS
            with DDGS() as ddg:
                items = list(ddg.text(query, max_results=max_results))
            results = [
                {"title": i.get("title"), "url": i.get("href"), "snippet": (i.get("body") or "")[:600]}
                for i in items
            ]
    except Exception as exc:
        return {"status": "error", "backend": backend, "query": query, "error": str(exc)}
    return {"status": "ok", "backend": backend, "query": query, "results": results}


# --------------------------------------------------------------------------- 3. revenue chart
def generate_revenue_chart(
    company_name: str,
    start_year: int,
    bear_case: list[float],
    base_case: list[float],
    bull_case: list[float],
    currency_unit: str,
    tool_context: ToolContext,
) -> dict:
    """Render Bear/Base/Bull revenue projections as a PNG chart and save it for the report.

    Args:
        company_name: Startup name.
        start_year: First projected year, e.g. 2026.
        bear_case: Revenue per year for the bear scenario (same length for all three cases).
        base_case: Revenue per year for the base scenario.
        bull_case: Revenue per year for the bull scenario.
        currency_unit: Label for the values, e.g. "USD M" or "INR Cr".
    """
    n = min(len(bear_case), len(base_case), len(bull_case))
    if n < 2:
        return {"status": "error", "error": "Need at least 2 years for each scenario."}
    years = [int(start_year) + i for i in range(n)]
    series = {
        "Bear": (bear_case[:n], BEAR),
        "Base": (base_case[:n], BASE),
        "Bull": (bull_case[:n], BULL),
    }

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
    ax.fill_between(years, series["Bear"][0], series["Bull"][0], color=BASE, alpha=0.07, label="Bear-Bull range")
    for label, (vals, color) in series.items():
        ax.plot(years, vals, marker="o", lw=2.6 if label == "Base" else 1.8, color=color, label=label)
        ax.annotate(
            f"{vals[-1]:,.1f}",
            (years[-1], vals[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=color,
            fontweight="bold",
        )

    def cagr(v):
        return ((v[-1] / v[0]) ** (1 / (n - 1)) - 1) * 100 if v[0] > 0 else float("nan")

    ax.set_title(f"{company_name} - Revenue Projections ({years[0]}-{years[-1]})", fontsize=14,
                 fontweight="bold", color=NAVY, loc="left")
    ax.set_ylabel(f"Revenue ({currency_unit})", color=SLATE)
    ax.set_xticks(years)
    ax.grid(axis="y", alpha=0.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    ax.text(
        0.99, 0.02,
        "CAGR  Bear {:.0f}% | Base {:.0f}% | Bull {:.0f}%".format(
            cagr(series["Bear"][0]), cagr(series["Base"][0]), cagr(series["Bull"][0])),
        transform=ax.transAxes, ha="right", fontsize=9, color=SLATE,
    )
    fig.tight_layout()

    out = _output_dir(tool_context, company_name) / "revenue_projections.png"
    fig.savefig(out)
    plt.close(fig)

    if getattr(tool_context, "state", None) is not None:
        tool_context.state["chart_path"] = str(out)
    return {"status": "ok", "chart_path": str(out), "years": years,
            "base_cagr_pct": round(cagr(series["Base"][0]), 1)}


# --------------------------------------------------------------------------- 4. risk scores
RISK_CATEGORIES = ["Market", "Execution", "Financial", "Regulatory", "Exit"]


def record_risk_scores(
    market: int,
    execution: int,
    financial: int,
    regulatory: int,
    exit_risk: int,
    tool_context: ToolContext,
) -> dict:
    """Save risk scores (1 = low risk, 10 = very high risk) for the five categories and render a risk chart.

    Args:
        market: Market risk score 1-10.
        execution: Execution / team risk score 1-10.
        financial: Financial / burn risk score 1-10.
        regulatory: Regulatory / legal risk score 1-10.
        exit_risk: Exit / liquidity risk score 1-10.
    """
    scores = [max(1, min(10, int(s))) for s in (market, execution, financial, regulatory, exit_risk)]
    overall = round(sum(scores) / len(scores), 1)

    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    colors = [BULL if s <= 3 else ("#B45309" if s <= 6 else BEAR) for s in scores]
    ax.barh(RISK_CATEGORIES[::-1], scores[::-1], color=colors[::-1], height=0.55)
    for i, s in enumerate(scores[::-1]):
        ax.text(s + 0.15, i, str(s), va="center", fontsize=10, fontweight="bold", color=NAVY)
    ax.set_xlim(0, 10.8)
    ax.set_xlabel("Risk score (1 = low, 10 = high)", color=SLATE)
    ax.set_title(f"Risk profile - overall {overall}/10", loc="left", fontsize=12, fontweight="bold", color=NAVY)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    company = _state(tool_context, "company_name", "startup")
    out = _output_dir(tool_context, company) / "risk_profile.png"
    fig.savefig(out)
    plt.close(fig)

    result = dict(zip([c.lower() for c in RISK_CATEGORIES], scores))
    if getattr(tool_context, "state", None) is not None:
        tool_context.state["risk_scores"] = result
        tool_context.state["risk_overall"] = overall
        tool_context.state["risk_chart_path"] = str(out)
    return {"status": "ok", "scores": result, "overall": overall, "risk_chart_path": str(out)}


# --------------------------------------------------------------------------- 5. HTML report
REPORT_CSS = """
:root{--navy:#0B1F3A;--teal:#0F766E;--ink:#1E293B;--muted:#64748B;--line:#E2E8F0;--bg:#F8FAFC}
*{box-sizing:border-box}body{margin:0;font-family:Georgia,'Times New Roman',serif;color:var(--ink);background:var(--bg);line-height:1.6}
.wrap{max-width:980px;margin:0 auto;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06)}
header{background:var(--navy);color:#fff;padding:48px 56px 36px}
header .kicker{font:600 12px/1 Arial,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#7DD3FC}
header h1{font-size:38px;margin:12px 0 6px;font-weight:normal}
header .meta{font:13px Arial,sans-serif;color:#CBD5E1}
.verdict{display:flex;gap:16px;flex-wrap:wrap;padding:24px 56px;border-bottom:1px solid var(--line);font-family:Arial,sans-serif}
.tile{flex:1;min-width:160px;border-left:4px solid var(--teal);padding:6px 14px}
.tile .k{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:22px;font-weight:700;color:var(--navy)}
section{padding:28px 56px;border-bottom:1px solid var(--line)}
section h2{font:700 13px Arial,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--teal);margin:0 0 14px}
section h3{color:var(--navy);font-size:18px}
.exec{background:#F0FDFA;font-size:17px}
table{border-collapse:collapse;width:100%;font:14px Arial,sans-serif;margin:12px 0}
th{background:var(--navy);color:#fff;text-align:left;padding:8px 10px}
td{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top}
img{max-width:100%;border:1px solid var(--line);margin:8px 0}
footer{padding:20px 56px;font:12px Arial,sans-serif;color:var(--muted)}
@media print{body{background:#fff}.wrap{box-shadow:none}}
"""


def generate_html_report(
    company_name: str,
    recommendation: str,
    conviction: str,
    proposed_valuation: str,
    executive_summary: str,
    tool_context: ToolContext,
) -> dict:
    """Assemble the McKinsey-style HTML due-diligence report from all prior agent outputs in session state.

    Args:
        company_name: Startup name.
        recommendation: One of "STRONG INVEST", "INVEST", "WATCH", "PASS".
        conviction: "High", "Medium" or "Low".
        proposed_valuation: Short valuation view, e.g. "USD 40-55M pre-money" or "Not enough data".
        executive_summary: 4-6 sentence executive summary in markdown.
    """
    def render(key: str) -> str:
        text = _state(tool_context, key)
        return md.markdown(text, extensions=["tables", "sane_lists"]) if text else "<p><em>Not available.</em></p>"

    chart = _img_b64(_state(tool_context, "chart_path"))
    risk_chart = _img_b64(_state(tool_context, "risk_chart_path"))
    overall_risk = _state(tool_context, "risk_overall", "n/a")
    today = dt.date.today().strftime("%d %B %Y")
    model_line = html.escape(config.describe())

    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(company_name)} - Investment Due Diligence</title><style>{REPORT_CSS}</style></head>
<body><div class="wrap">
<header><div class="kicker">Confidential - Investment Committee Memo</div>
<h1>{html.escape(company_name)}</h1>
<div class="meta">Venture due diligence report &middot; {today} &middot; Prepared by the AI VC Due Diligence Agent Team</div></header>
<div class="verdict">
<div class="tile"><div class="k">Recommendation</div><div class="v">{html.escape(recommendation)}</div></div>
<div class="tile"><div class="k">Conviction</div><div class="v">{html.escape(conviction)}</div></div>
<div class="tile"><div class="k">Overall risk</div><div class="v">{overall_risk}/10</div></div>
<div class="tile"><div class="k">Valuation view</div><div class="v" style="font-size:16px">{html.escape(proposed_valuation)}</div></div>
</div>
<section class="exec"><h2>Executive summary</h2>{md.markdown(executive_summary)}</section>
<section><h2>1. Company overview</h2>{render("company_profile")}</section>
<section><h2>2. Market analysis</h2>{render("market_analysis")}</section>
<section><h2>3. Financial model</h2>
{f'<img alt="Revenue projections" src="data:image/png;base64,{chart}">' if chart else ''}
{render("financial_model")}</section>
<section><h2>4. Risk assessment</h2>
{f'<img alt="Risk profile" src="data:image/png;base64,{risk_chart}">' if risk_chart else ''}
{render("risk_assessment")}</section>
<section><h2>5. Investment memo</h2>{render("investment_memo")}</section>
<footer>Generated automatically ({model_line}). AI-generated research may contain errors; verify all figures
with primary sources before any investment decision. Not investment advice.</footer>
</div></body></html>"""

    out = _output_dir(tool_context, company_name) / f"{_slug(company_name)}_due_diligence_report.html"
    out.write_text(body, encoding="utf-8")
    if getattr(tool_context, "state", None) is not None:
        tool_context.state["report_path"] = str(out)
    return {"status": "ok", "report_path": str(out)}


# --------------------------------------------------------------------------- 6. infographic
def _local_infographic(path: Path, company_name, tagline, recommendation, metrics, strengths, risks):
    """Deterministic matplotlib infographic - used when no image model is available."""
    fig = plt.figure(figsize=(9, 12), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0.84), 1, 0.16, color=NAVY))
    ax.text(0.06, 0.94, "VC DUE DILIGENCE - TL;DR", color="#7DD3FC", fontsize=11, fontweight="bold")
    ax.text(0.06, 0.895, company_name, color="white", fontsize=28, fontweight="bold")
    ax.text(0.06, 0.857, tagline[:80], color="#CBD5E1", fontsize=11)

    rec_color = {"STRONG INVEST": BULL, "INVEST": BULL, "WATCH": "#B45309", "PASS": BEAR}.get(
        recommendation.upper(), TEAL)
    ax.add_patch(plt.Rectangle((0.06, 0.76), 0.88, 0.055, color=rec_color))
    ax.text(0.5, 0.787, f"VERDICT: {recommendation.upper()}", color="white", fontsize=16,
            fontweight="bold", ha="center", va="center")

    # metric tiles (2 x 3)
    for i, m in enumerate(metrics[:6]):
        col, row = i % 3, i // 3
        x, y = 0.06 + col * 0.30, 0.64 - row * 0.10
        ax.add_patch(plt.Rectangle((x, y), 0.28, 0.085, color="#F1F5F9"))
        label, _, value = m.partition(":")
        ax.text(x + 0.015, y + 0.058, label.strip()[:22].upper(), fontsize=8, color=SLATE, fontweight="bold")
        ax.text(x + 0.015, y + 0.02, (value.strip() or label)[:18], fontsize=14, color=NAVY, fontweight="bold")

    def bullets(title, items, y, color):
        ax.text(0.06, y, title, fontsize=13, fontweight="bold", color=color)
        for j, item in enumerate(items[:4]):
            ax.text(0.08, y - 0.04 - j * 0.04, "-  " + item[:78], fontsize=10.5, color=NAVY)

    bullets("WHY IT COULD WIN", strengths, 0.49, BULL)
    bullets("KEY RISKS", risks, 0.28, BEAR)
    ax.text(0.06, 0.02, "AI-generated summary - verify before investing. Not investment advice.",
            fontsize=8, color=SLATE)
    fig.savefig(path)
    plt.close(fig)


def generate_infographic(
    company_name: str,
    tagline: str,
    recommendation: str,
    key_metrics: list[str],
    strengths: list[str],
    risks: list[str],
    tool_context: ToolContext,
) -> dict:
    """Create a one-page visual TL;DR infographic (Gemini image model, or a local matplotlib fallback).

    Args:
        company_name: Startup name.
        tagline: One-line description of what the company does.
        recommendation: "STRONG INVEST", "INVEST", "WATCH" or "PASS".
        key_metrics: Up to 6 "Label: Value" strings, e.g. "TAM: $18B", "ARR: $4.2M".
        strengths: Up to 4 short bullet points on why it could win.
        risks: Up to 4 short bullet points on key risks.
    """
    out_dir = _output_dir(tool_context, company_name)
    path = out_dir / "infographic.png"
    engine = config.IMAGE_PROVIDER
    note = ""

    if engine == "gemini":
        try:
            from google import genai
            from google.genai import types

            prompt = (
                "Design a clean, professional one-page investment infographic (portrait, consulting style, "
                "navy and teal palette, white background, crisp sans-serif typography, no stock photos). "
                f"Title: '{company_name}'. Subtitle: '{tagline}'. "
                f"Large verdict banner: '{recommendation}'. "
                f"Metric tiles: {'; '.join(key_metrics[:6])}. "
                f"Section 'Why it could win': {'; '.join(strengths[:4])}. "
                f"Section 'Key risks': {'; '.join(risks[:4])}. "
                "Spell every word exactly as given. Footer: 'AI-generated - not investment advice'."
            )
            client = genai.Client()
            resp = client.models.generate_content(
                model=config.GEMINI_IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            image_bytes = None
            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if not image_bytes:
                raise RuntimeError("image model returned no image")
            path.write_bytes(image_bytes)
        except Exception as exc:
            note = f"Gemini image generation failed ({exc}); used local renderer."
            engine = "local"

    if engine != "gemini":
        _local_infographic(path, company_name, tagline, recommendation, key_metrics, strengths, risks)

    if getattr(tool_context, "state", None) is not None:
        tool_context.state["infographic_path"] = str(path)
    return {"status": "ok", "engine": engine, "infographic_path": str(path), "note": note}


# --------------------------------------------------------------------------- 7. executive PDF
def generate_executive_pdf(
    company_name: str,
    recommendation: str,
    conviction: str,
    proposed_valuation: str,
    headline: str,
    situation: str,
    complication: str,
    resolution: str,
    key_takeaways: list[str],
    investment_thesis: list[str],
    return_scenarios: list[str],
    key_metrics: list[str],
    company_facts: list[str],
    market_headline: str,
    market_sizing: list[str],
    competitors: list[str],
    moat_assessment: list[str],
    market_insights: list[str],
    financial_headline: str,
    financial_highlights: list[str],
    unit_economics: list[str],
    risk_headline: str,
    top_risks: list[str],
    next_steps: list[str],
    tool_context: ToolContext,
) -> dict:
    """Build a BCG/McKinsey-style 4-page executive PDF brief from the team's artifacts (charts are added automatically).

    Args:
        company_name: Startup name.
        recommendation: "STRONG INVEST", "INVEST", "WATCH" or "PASS".
        conviction: "High", "Medium" or "Low".
        proposed_valuation: Short valuation view, e.g. "USD 40-55M pre-money".
        headline: Page-1 action title - one sentence stating the overall so-what (max 25 words).
        situation: 1-2 sentences - the context (what the company is, where it stands).
        complication: 1-2 sentences - the tension or key question for investors.
        resolution: 1-2 sentences - the answer / recommendation and why.
        key_takeaways: 3-5 one-sentence takeaways.
        investment_thesis: 3-4 pillars "Pillar title | one-sentence evidence".
        return_scenarios: 3 rows "Bear|Base|Bull | exit value | MOIC | key assumption".
        key_metrics: 6 "Label: Value" items, e.g. "TAM: $18B", "ARR: $4.0M", "Overall risk: 4.6/10".
        company_facts: Up to 9 "Label: Value" items (Founded, HQ, Stage, Total funding, Lead investors, Team, ...).
        market_headline: Page-2 action title (one sentence so-what about the market and positioning).
        market_sizing: 3 "Label: Value" items: TAM, SAM, SOM with short basis, e.g. "TAM: $18B (2026, global)".
        competitors: Up to 6 rows "Name | scale/positioning | how the target differs".
        moat_assessment: 3-5 rows "Dimension | High/Medium/Low | evidence" (e.g. data, network effects,
            switching costs, brand, regulation, technology).
        market_insights: 3-5 one-sentence insights (drivers, why now).
        financial_headline: Page-3 action title (one sentence so-what about the financial outlook).
        financial_highlights: 3-5 one-sentence highlights (baseline, scenario CAGRs, capital needs, valuation).
        unit_economics: Up to 8 "Label: Value" items (CAC, LTV, LTV/CAC, gross margin, payback, burn multiple).
        risk_headline: Page-4 action title (one sentence so-what about the risk profile).
        top_risks: Up to 6 rows "Category | key risk | mitigation or diligence ask".
        next_steps: 3-6 concrete next diligence steps.
    """
    import json

    from .pdf_report import build_executive_pdf

    brief = {k: v for k, v in locals().items() if k not in {"tool_context", "json", "build_executive_pdf"}}
    out_dir = _output_dir(tool_context, company_name)
    (out_dir / "executive_brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")

    images = {
        "chart": _state(tool_context, "chart_path") or str(out_dir / "revenue_projections.png"),
        "risk_chart": _state(tool_context, "risk_chart_path") or str(out_dir / "risk_profile.png"),
    }
    path = out_dir / f"{_slug(company_name)}_executive_brief.pdf"
    try:
        build_executive_pdf(path, brief, images)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    if getattr(tool_context, "state", None) is not None:
        tool_context.state["pdf_path"] = str(path)
    return {"status": "ok", "pdf_path": str(path), "pages": 4}
