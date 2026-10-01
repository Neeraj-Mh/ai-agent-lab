"""Command-line runner for the AI VC Due Diligence Agent Team.

Examples:
    python run.py "Razorpay"
    python run.py https://www.zepto.com
    python run.py "Sarvam AI https://www.sarvam.ai - focus on enterprise traction"
    python run.py "Acme" --provider claude
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid

APP_NAME = "vc_due_diligence"
STEP_LABELS = {
    "intake_agent": "1/9 Intake - resolving startup & reading website",
    "company_research_agent": "2/9 Company research - founders, funding, product, traction",
    "market_analysis_agent": "3/9 Market analysis - TAM/SAM, competitors, positioning",
    "financial_model_agent": "4/9 Financial model - bear/base/bull projections",
    "risk_assessment_agent": "5/9 Risk assessment - 5 categories",
    "investment_memo_agent": "6/9 Investment memo - thesis & recommendation",
    "report_agent": "7/9 HTML report",
    "infographic_agent": "8/9 Visual TL;DR infographic",
    "executive_pdf_agent": "9/9 Executive PDF brief (BCG/McKinsey style)",
}


async def main(query: str) -> int:
    # Imported here so --provider can set the env var before config loads.
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from vc_due_diligence import config
    from vc_due_diligence.agent import root_agent

    print(f"\nAI VC Due Diligence Agent Team  [{config.describe()}]")
    print(f"Target: {query}\n")

    sessions = InMemorySessionService()
    user_id, session_id = "analyst", str(uuid.uuid4())
    await sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=sessions)

    message = types.Content(role="user", parts=[types.Part(text=query)])
    current, started = None, time.time()
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        if event.author != current and event.author in STEP_LABELS:
            current = event.author
            print(f"[{time.time() - started:6.0f}s] > {STEP_LABELS[current]}")
        for call in event.get_function_calls() or []:
            print(f"           tool: {call.name}")
        if event.error_message:
            print(f"           ! {event.error_message}")

    session = await sessions.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    state = session.state
    print(f"\nDone in {time.time() - started:.0f}s\n")
    print("Final summary:\n" + str(state.get("executive_pdf_summary") or state.get("infographic_summary", "")).strip() + "\n")
    for label, key in [
        ("Output folder", "output_dir"),
        ("HTML report", "report_path"),
        ("Executive PDF", "pdf_path"),
        ("Revenue chart", "chart_path"),
        ("Risk chart", "risk_chart_path"),
        ("Infographic", "infographic_path"),
    ]:
        if state.get(key):
            print(f"  {label:<14} {state[key]}")

    # Also save the full investment memo as markdown next to the report.
    if state.get("output_dir") and state.get("investment_memo"):
        memo_path = os.path.join(state["output_dir"], "investment_memo.md")
        with open(memo_path, "w", encoding="utf-8") as fh:
            fh.write(state["investment_memo"])
        print(f"  {'Memo (md)':<14} {memo_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run VC due diligence on a startup name or URL.")
    parser.add_argument("query", nargs="+", help="Startup name and/or website URL (plus optional context)")
    parser.add_argument("--provider", choices=["gemini", "claude"], help="Override LLM_PROVIDER from .env")
    args = parser.parse_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    sys.exit(asyncio.run(main(" ".join(args.query))))
