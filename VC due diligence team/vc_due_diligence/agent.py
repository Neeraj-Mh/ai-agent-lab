"""AI VC Due Diligence Agent Team (Google ADK, works with Gemini or Claude).

Pipeline (SequentialAgent), each step writes its result into session state:

  intake_agent            -> startup_brief        (name/URL resolution, website read)
  company_research_agent  -> company_profile      (founders, funding, product, traction)
  market_analysis_agent   -> market_analysis      (TAM/SAM/SOM, competitors, positioning)
  financial_model_agent   -> financial_model      (bear/base/bull revenue + unit economics, chart)
  risk_assessment_agent   -> risk_assessment      (5 risk categories, scored + chart)
  investment_memo_agent   -> investment_memo      (thesis, valuation view, recommendation)
  report_agent            -> report_summary       (McKinsey-style HTML report)
  infographic_agent       -> infographic_summary  (visual TL;DR PNG)

Note: text inside instructions uses ADK state templating, so curly braces are only
used for state keys.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent

from . import config
from .tools import (
    fetch_webpage,
    generate_html_report,
    generate_infographic,
    generate_revenue_chart,
    record_risk_scores,
    register_startup,
    web_search,
)

FAST = config.build_model("fast")
DEEP = config.build_model("deep")

# Live research tools depend on the provider:
#  - Gemini: built-in Google Search grounding (must be the agent's only tool)
#  - Claude (or SEARCH_BACKEND=tavily/duckduckgo): web_search + fetch_webpage function tools
if config.SEARCH_BACKEND == "google":
    from google.adk.tools import google_search

    RESEARCH_TOOLS = [google_search]
    SEARCH_HINT = "Use Google Search for every fact you report."
else:
    RESEARCH_TOOLS = [web_search, fetch_webpage]
    SEARCH_HINT = (
        "Use the web_search tool (max_results 6-8) several times with different queries, and "
        "fetch_webpage to read the most relevant pages in full."
    )

CITE = (
    "Cite sources inline as markdown links. If a figure cannot be verified, say 'not disclosed' "
    "or give a clearly labelled estimate with your reasoning - never invent numbers."
)

# ----------------------------------------------------------------------------- 1. Intake
intake_agent = LlmAgent(
    name="intake_agent",
    model=FAST,
    description="Resolves the startup name/URL and reads the company website.",
    instruction="""You are the intake analyst of a venture capital due-diligence team.
The user gives a startup name, a website URL, or both (possibly with extra context).

Steps:
1. Work out the company name and website. If only a URL is given, derive the name from the site.
2. Call register_startup exactly once with the company name and website ("unknown" if none).
3. If a website is known, call fetch_webpage on it, and on up to 2 useful sub-pages from key_links
   (About, Pricing, Customers, Team).
4. Write a concise STARTUP BRIEF in markdown:
   - Company name, website, one-line description
   - What the product does and who it is for (from the website)
   - Any founders, customers, pricing, or traction claims found on the site
   - Open questions for the research team
If the site cannot be fetched, say so and continue with what the user provided.""",
    tools=[register_startup, fetch_webpage],
    output_key="startup_brief",
)

# ----------------------------------------------------------------------------- 2. Company research
company_research_agent = LlmAgent(
    name="company_research_agent",
    model=FAST,
    description="Researches founders, funding, product and traction with live web search.",
    instruction=f"""You are a senior VC associate doing company research.

Startup brief from intake:
{{startup_brief}}

{SEARCH_HINT}
Research and report in markdown with these headings:
## Snapshot  (founded, HQ, stage, headcount, business model)
## Founders & team  (backgrounds, prior exits, domain fit)
## Funding history  (table: round | date | amount | lead investors)
## Product  (what it does, differentiation, technology moat)
## Traction  (revenue/ARR, users, customers, growth, partnerships, press)
## Red flags spotted
{CITE}""",
    tools=RESEARCH_TOOLS,
    output_key="company_profile",
)

# ----------------------------------------------------------------------------- 3. Market analysis
market_analysis_agent = LlmAgent(
    name="market_analysis_agent",
    model=FAST,
    description="Sizes the market and maps competitors and positioning.",
    instruction=f"""You are a market strategist at a VC fund.

Company research so far:
{{company_profile}}

{SEARCH_HINT}
Produce a markdown market analysis:
## Market definition
## Market size  (TAM, SAM, SOM with method: top-down from reports AND a bottom-up sanity check)
## Growth drivers & headwinds
## Competitive landscape  (table: competitor | funding/scale | positioning | key difference)
## Positioning & moat  (where this startup wins or loses; 2x2 positioning described in words)
## Why now?
{CITE}""",
    tools=RESEARCH_TOOLS,
    output_key="market_analysis",
)

# ----------------------------------------------------------------------------- 4. Financial model
financial_model_agent = LlmAgent(
    name="financial_model_agent",
    model=DEEP,
    description="Builds bear/base/bull revenue projections and unit economics, renders the chart.",
    instruction="""You are a VC financial analyst. Build a simple, defensible 5-year model.

Company research:
{company_profile}

Market analysis:
{market_analysis}

Steps:
1. Establish the current revenue baseline (reported figure, or an estimate from headcount, pricing,
   customers or funding stage - state the method clearly).
2. Define Bear / Base / Bull assumptions (growth rates, pricing, customer adds, churn).
3. Call generate_revenue_chart once with 5 yearly values per scenario starting next calendar year
   and an appropriate currency_unit (e.g. "USD M" or "INR Cr").
4. Write the model in markdown:
## Revenue baseline
## Scenario assumptions  (table: driver | bear | base | bull)
## 5-year projections  (table: year | bear | base | bull)
## Unit economics  (CAC, LTV, LTV/CAC, gross margin, payback, burn multiple - estimate where needed)
## Capital needs & runway
## Implied valuation range  (revenue multiples from comparable companies)
Mark every estimate as an estimate.""",
    tools=[generate_revenue_chart],
    output_key="financial_model",
)

# ----------------------------------------------------------------------------- 5. Risk assessment
risk_assessment_agent = LlmAgent(
    name="risk_assessment_agent",
    model=DEEP,
    description="Scores risk across market, execution, financial, regulatory and exit categories.",
    instruction="""You are the fund's risk partner. Be sceptical and specific.

Company research:
{company_profile}

Market analysis:
{market_analysis}

Financial model:
{financial_model}

Assess five categories: Market, Execution, Financial, Regulatory, Exit.
For each: score 1 (low risk) to 10 (very high risk), the 2-3 most important risks, likelihood,
impact, and a mitigation or diligence question for the founders.

First call record_risk_scores once with the five scores. Then write markdown:
## Risk scorecard  (table: category | score | top risk | mitigation)
## Detailed analysis  (one sub-heading per category)
## Deal-breakers  (anything that alone would justify a PASS)
## Questions for management  (8-10 sharp questions)""",
    tools=[record_risk_scores],
    output_key="risk_assessment",
)

# ----------------------------------------------------------------------------- 6. Investment memo
investment_memo_agent = LlmAgent(
    name="investment_memo_agent",
    model=DEEP,
    description="Synthesises everything into a structured investment memo and recommendation.",
    instruction="""You are the General Partner writing the investment committee memo.

Startup brief:
{startup_brief}

Company research:
{company_profile}

Market analysis:
{market_analysis}

Financial model:
{financial_model}

Risk assessment:
{risk_assessment}

Write the memo in markdown:
## Recommendation  (one of STRONG INVEST / INVEST / WATCH / PASS, conviction High/Medium/Low, one-line why)
## Investment thesis  (3-5 numbered pillars, each backed by evidence)
## What you have to believe  (key assumptions for the base case)
## Valuation & deal terms  (proposed entry valuation range, cheque size, ownership target, key terms)
## Return scenarios  (bear/base/bull exit value and MOIC)
## Key risks & mitigants
## Next diligence steps
Be decisive and consistent with the risk scores and the model.""",
    output_key="investment_memo",
)

# ----------------------------------------------------------------------------- 7. HTML report
report_agent = LlmAgent(
    name="report_agent",
    model=FAST,
    description="Publishes the McKinsey-style HTML due-diligence report.",
    instruction="""You produce the final due-diligence report.

Investment memo:
{investment_memo}

Call generate_html_report exactly once with:
- company_name
- recommendation and conviction exactly as stated in the memo
- proposed_valuation: a short phrase from the memo's valuation section
- executive_summary: 4-6 crisp sentences (what the company does, why it matters, the verdict,
  biggest upside, biggest risk)
The tool pulls the detailed sections from the team's work automatically.
Afterwards reply with the report path and the executive summary.""",
    tools=[generate_html_report],
    output_key="report_summary",
)

# ----------------------------------------------------------------------------- 8. Infographic
infographic_agent = LlmAgent(
    name="infographic_agent",
    model=FAST,
    description="Creates the visual TL;DR infographic.",
    instruction="""You create a one-page visual TL;DR for busy partners.

Investment memo:
{investment_memo}

Market analysis:
{market_analysis}

Call generate_infographic exactly once with:
- company_name, a tagline (max 12 words) and the recommendation from the memo
- key_metrics: 6 short "Label: Value" items (e.g. TAM, ARR or revenue, total funding,
  base-case CAGR, overall risk, proposed valuation)
- strengths: 3-4 bullets (max 10 words each)
- risks: 3-4 bullets (max 10 words each)
Then reply with a final summary listing: recommendation, report path and infographic path.""",
    tools=[generate_infographic],
    output_key="infographic_summary",
)

# ----------------------------------------------------------------------------- Team
root_agent = SequentialAgent(
    name="vc_due_diligence_team",
    description=(
        "AI VC due-diligence team: give it a startup name or website URL and it researches the company "
        "and market, models revenue, scores risk, writes an investment memo, an HTML report and an infographic."
    ),
    sub_agents=[
        intake_agent,
        company_research_agent,
        market_analysis_agent,
        financial_model_agent,
        risk_assessment_agent,
        investment_memo_agent,
        report_agent,
        infographic_agent,
    ],
)
