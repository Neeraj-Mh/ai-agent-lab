# AI VC Due Diligence Agent Team

A multi-agent team of nine specialist agents that does first-pass venture-capital due diligence on any startup. You give it a **company name or website URL**, and it researches the company live on the web. It then models the financials, scores the risk and writes an investment memo. The outputs are a **consulting-style HTML report**, a **BCG/McKinsey-style 4-page executive PDF**, a **revenue chart** and a **visual TL;DR infographic**.

It is built on **Google ADK** and is **multi-provider**: the same team runs on **Gemini** or **Claude**, and you choose with one setting.

```
python run.py https://www.example-startup.com            # Gemini (default)
python run.py "Example Startup" --provider claude         # Claude
```

---

## Features

| | Feature | What you get |
|---|---|---|
| 🔍 | **Live research** | Real-time web search for company and market data, with sources cited inline |
| 🌐 | **URL support** | Paste any startup website; the team reads the homepage plus its About, Pricing and Customers pages |
| 📈 | **Revenue charts** | Bear/Base/Bull 5-year projection chart with CAGR, drawn with matplotlib |
| 🧠 | **Deep risk analysis** | Scored 1-10 across 5 categories (Market, Execution, Financial, Regulatory, Exit), with a risk chart |
| 📄 | **Professional reports** | Consulting-style HTML investment report (print to PDF straight from the browser) |
| 📑 | **Executive PDF brief** | A 4-page PDF for the investment committee, written as action titles in the BCG/McKinsey style. It covers the verdict, Situation-Complication-Resolution, thesis pillars, return scenarios, TAM/SAM/SOM circles, a moat scorecard, charts, risks and next steps |
| 🎨 | **Visual TL;DR** | One-page infographic: AI-generated with the Gemini image model, or rendered locally |
| 🔀 | **Gemini or Claude** | Switch the model provider with `LLM_PROVIDER`; you can also mix models per tier |

---

## Use case

**Who it's for:** VC and angel analysts, corporate-venture and strategy teams, startup founders who want to stress-test their own pitch, and bank, NBFC and fintech partnership teams evaluating vendors.

**The problem:** the first screen of a deal usually takes an analyst 1–3 days. That time goes on reading the website, searching for funding news, sizing the market, mapping competitors, sketching a model, listing risks and writing a memo. Most deals get passed on, so much of that effort is thrown away.

**What this team does:** in about 5–10 minutes it produces the first-screen pack that an analyst would bring to a Monday partner meeting:

1. **Researches the company**: founders, funding rounds, product, traction
2. **Analyses the market**: TAM/SAM/SOM (top-down plus a bottom-up check), competitors, positioning, "why now"
3. **Builds the financial model**: revenue baseline, scenario assumptions, 5-year Bear/Base/Bull projections, unit economics, implied valuation
4. **Assesses risks**: market, execution, financial, regulatory and exit, each scored, with mitigations and questions for founders
5. **Writes the investment memo**: recommendation (STRONG INVEST / INVEST / WATCH / PASS), thesis, valuation and terms, return scenarios
6. **Creates the HTML report**: one shareable, printable document
7. **Generates the infographic**: a one-glance visual summary for busy partners
8. **Writes the executive PDF brief**: 4 pages in the BCG/McKinsey style, ready to email to the investment committee

### Benefits

- **Speed:** first-screen diligence drops from days to minutes, so you can screen 10x more deals.
- **Consistency:** every deal goes through the same 9-step framework and the same 5-category risk scorecard, which makes deals comparable.
- **Traceability:** facts carry source links, and estimates are labelled as estimates with their method.
- **Decision-ready output:** the verdict, conviction, valuation view and questions for management are all in the report.
- **Board-ready format:** the 4-page executive PDF follows how strategy consultancies brief leadership: answer first, action titles, one idea per page.
- **Vendor flexibility:** you can run on Gemini or Claude, change models without touching code, and fall back to free search and a local infographic when keys are missing.

> ⚠️ AI-generated research can be wrong or out of date. Treat the output as a starting point for human diligence. It is not investment advice.

---

## How it works

```
 startup name / URL
        │
        ▼
┌───────────────────┐   register_startup, fetch_webpage
│ 1. intake_agent   │──────────────────────────────────────► startup_brief
└───────────────────┘
┌───────────────────┐   Google Search (Gemini) or web_search + fetch_webpage (Claude)
│ 2. company_research│─────────────────────────────────────► company_profile
└───────────────────┘
┌───────────────────┐   live search
│ 3. market_analysis │─────────────────────────────────────► market_analysis
└───────────────────┘
┌───────────────────┐   generate_revenue_chart  ──► revenue_projections.png
│ 4. financial_model │─────────────────────────────────────► financial_model
└───────────────────┘
┌───────────────────┐   record_risk_scores      ──► risk_profile.png
│ 5. risk_assessment │─────────────────────────────────────► risk_assessment
└───────────────────┘
┌───────────────────┐   (deep reasoning model)
│ 6. investment_memo │─────────────────────────────────────► investment_memo
└───────────────────┘
┌───────────────────┐   generate_html_report    ──► <company>_due_diligence_report.html
│ 7. report_agent   │
└───────────────────┘
┌───────────────────┐   generate_infographic    ──► infographic.png
│ 8. infographic    │
└───────────────────┘
┌───────────────────┐   generate_executive_pdf  ──► <company>_executive_brief.pdf (4 pages)
│ 9. executive_pdf  │                              + executive_brief.json (editable)
└───────────────────┘
```

- **Orchestration:** an ADK `SequentialAgent`. Each agent writes its output to shared session state (`output_key`), and the next agent reads it through `{state}` placeholders in its instructions.
- **Two model tiers:** a *fast* model handles intake, research, the report and the infographic. A *deep* model handles the financials, risk and memo.
- **Token-efficient tools:** the report tool reads the long sections straight from session state instead of having the LLM repeat them as tool arguments.

| Agent | Model tier | Tools | Output |
|---|---|---|---|
| intake_agent | fast | register_startup, fetch_webpage | startup_brief |
| company_research_agent | fast | live search | company_profile |
| market_analysis_agent | fast | live search | market_analysis |
| financial_model_agent | deep | generate_revenue_chart | financial_model + chart |
| risk_assessment_agent | deep | record_risk_scores | risk_assessment + risk chart |
| investment_memo_agent | deep | none | investment_memo |
| report_agent | fast | generate_html_report | HTML report |
| infographic_agent | fast | generate_infographic | infographic.png |
| executive_pdf_agent | deep | generate_executive_pdf | 4-page executive PDF + executive_brief.json |

### Gemini vs Claude: what changes

| | `LLM_PROVIDER=gemini` | `LLM_PROVIDER=claude` |
|---|---|---|
| Default fast / deep models | `gemini-3.5-flash` / `gemini-3.1-pro-preview` | `claude-sonnet-5-5` / `claude-opus-5-5` |
| How ADK calls the model | Native | Through ADK's `LiteLlm` bridge (`anthropic/<model>`) |
| Live search | Built-in Google Search grounding | `web_search` tool (Tavily if `TAVILY_API_KEY` is set, otherwise free DuckDuckGo) plus `fetch_webpage` |
| Infographic | Gemini image model | Gemini image model if `GOOGLE_API_KEY` is also set, otherwise the local matplotlib renderer |

You can override any model with `FAST_MODEL` / `DEEP_MODEL`, for example a cheaper `claude-haiku-4-5-20251001` for the fast tier.

---

## Project structure

```
VC due diligence team/
├── README.md
├── requirements.txt
├── .env.example            # copy to .env and add your keys
├── run.py                  # command-line runner (progress log + output paths)
├── make_pdf.py             # rebuild the executive PDF from a run folder (no LLM, no keys)
├── vc_due_diligence/       # the ADK agent package (works with `adk web`)
│   ├── __init__.py
│   ├── agent.py            # the 8 agents + SequentialAgent root_agent
│   ├── config.py           # provider/model/search/image switches
│   ├── tools.py            # URL reader, search, chart, risk, HTML report, infographic, PDF tool
│   └── pdf_report.py       # reportlab layout for the 4-page executive brief
├── examples/               # sample outputs (fictional company, for illustration)
└── outputs/                # one folder per run (git-ignored)
```

---

## How to run

### 1. Prerequisites
- Python **3.10+**
- At least one API key:
  - **Gemini:** a free key from [Google AI Studio](https://aistudio.google.com/apikey)
  - **Claude:** a key from the [Claude Console](https://platform.claude.com)
- Optional: a [Tavily](https://tavily.com) key for higher-quality search in Claude mode

### 2. Install

```bash
cd "VC due diligence team"
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
copy .env.example .env      # Windows   (macOS/Linux: cp .env.example .env)
```

Edit `.env`:

```ini
LLM_PROVIDER=gemini          # or claude
GOOGLE_API_KEY=...           # needed for Gemini (and for AI infographics)
ANTHROPIC_API_KEY=...        # needed for Claude
```

### 4a. Run from the command line

```bash
python run.py "Razorpay"
python run.py https://www.sarvam.ai
python run.py "Zepto https://www.zeptonow.com - focus on unit economics"
python run.py "Razorpay" --provider claude      # one-off switch to Claude
```

Example progress log:

```
AI VC Due Diligence Agent Team  [provider=claude | fast=claude-sonnet-5-5 | deep=claude-opus-5-5 | search=duckduckgo | infographic=local]
[     0s] > 1/8 Intake - resolving startup & reading website
           tool: register_startup
           tool: fetch_webpage
[    14s] > 2/8 Company research - founders, funding, product, traction
...
  HTML report    outputs/razorpay_20261001-210512/razorpay_due_diligence_report.html
  Executive PDF  outputs/razorpay_20261001-210512/razorpay_executive_brief.pdf
  Infographic    outputs/razorpay_20261001-210512/infographic.png
```

### 4b. Or use the ADK web UI (chat + event trace)

```bash
cd "VC due diligence team"
adk web
```

Open http://localhost:8000, pick **vc_due_diligence**, and type a startup name or URL. You can inspect every agent's step, tool call and state change in the trace panel.

### 5. Outputs

Each run writes to `outputs/<company>_<timestamp>/`:

| File | What it is |
|---|---|
| `<company>_executive_brief.pdf` | **4-page BCG/McKinsey-style executive brief** (see below) |
| `executive_brief.json` | The PDF's content. Edit it and re-run `make_pdf.py` to regenerate |
| `<company>_due_diligence_report.html` | Full consulting-style report with charts embedded; open it in a browser and use Ctrl+P to save as PDF |
| `revenue_projections.png` | Bear/Base/Bull revenue chart |
| `risk_profile.png` | 5-category risk scorecard chart |
| `infographic.png` | Visual TL;DR |
| `investment_memo.md` | The memo as markdown (CLI runs) |

The `examples/` folder has sample outputs generated with made-up data for a fictional company, so you can see the format before running anything.

### 6. The executive PDF brief

The final agent acts as a strategy-consultancy engagement manager. It turns the team's work into a 4-page brief that follows consulting conventions: **every page opens with an action title** (a one-sentence "so what", not a topic label), the answer comes first, and the evidence follows.

| Page | Content |
|---|---|
| 1. Executive summary | Recommendation banner (colour-coded), 6 KPI tiles, Situation / Complication / Resolution, key takeaways, investment-thesis pillars, Bear/Base/Bull return scenarios with MOIC |
| 2. Company & market | Company fact sheet, TAM/SAM/SOM concentric circles, competitive landscape table, moat scorecard (High/Medium/Low), market insights |
| 3. Financial outlook | Bear/Base/Bull revenue chart, financial highlights, unit-economics table |
| 4. Risks & next steps | 5-category risk chart, top-risk table with mitigations, recommended next steps, methodology note |

- **Always 4 pages:** each page is laid out to shrink to fit, so long content never spills onto a fifth page.
- **Editable after the run:** the PDF content is saved to `executive_brief.json`. You can tweak a headline or fix a number, then rebuild without calling any LLM:

```bash
python make_pdf.py outputs/razorpay_20261001-210512
python make_pdf.py outputs/razorpay_20261001-210512 --out Razorpay_IC_brief.pdf
```

`make_pdf.py` only needs `reportlab`; it doesn't need ADK or API keys. A sample is in `examples/sample_executive_brief.pdf`.

---

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `claude` |
| `FAST_MODEL` / `DEEP_MODEL` | per provider (see above) | Override model IDs |
| `GOOGLE_API_KEY` | (none) | Gemini text and image models |
| `ANTHROPIC_API_KEY` | (none) | Claude models |
| `SEARCH_BACKEND` | `auto` | `google` (Gemini only), `tavily`, `duckduckgo` |
| `TAVILY_API_KEY` | (none) | Enables Tavily search |
| `IMAGE_PROVIDER` | `auto` | `gemini` (AI image) or `local` (matplotlib) |
| `GEMINI_IMAGE_MODEL` | `gemini-3.1-flash-image` | Image model for the infographic |
| `OUTPUT_DIR` | `./outputs` | Where run folders are written |

## Troubleshooting

- **`404 model not found`:** model names change over time. Set `FAST_MODEL` / `DEEP_MODEL` in `.env` to a model your key can access.
- **Claude mode returns thin research:** add a `TAVILY_API_KEY`, because DuckDuckGo results are rate-limited and shorter.
- **The infographic is the local style, not AI-generated:** set `GOOGLE_API_KEY` (and `IMAGE_PROVIDER=gemini`). If image generation fails, the tool falls back to the local renderer automatically, and the reason is recorded in the tool's `note` field.
- **A website won't load:** some sites block bots. The team continues with search results and records that the site could not be read.

## Extending

- Add a step such as a **cap-table agent** or **founder-reference agent**: write an `LlmAgent` in `agent.py` and insert it into `sub_agents`.
- Run the research and market agents side by side with ADK's `ParallelAgent` to save time.
- Swap in another LiteLLM provider (OpenAI, Mistral, Ollama) by extending `config.build_model`.

---

Part of [ai-agent-lab](../README.md), a collection of AI agents for banking, product-management and business-analysis use cases.
