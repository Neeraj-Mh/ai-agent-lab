"""Rebuild the 4-page executive PDF from a finished run folder - no LLM call needed.

Useful after you hand-edit `executive_brief.json` (tweak a headline, fix a number) or
after changing the PDF design in vc_due_diligence/pdf_report.py.

    python make_pdf.py outputs/razorpay_20261001-210512
    python make_pdf.py outputs/razorpay_20261001-210512 --out razorpay_ic_brief.pdf
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

# Load pdf_report.py directly so this script needs neither google-adk nor API keys.
_spec = importlib.util.spec_from_file_location(
    "pdf_report", Path(__file__).resolve().parent / "vc_due_diligence" / "pdf_report.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_executive_pdf = _mod.build_executive_pdf


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_folder", help="Folder created by a run, containing executive_brief.json")
    ap.add_argument("--out", help="Output PDF path (default: <company>_executive_brief.pdf in the run folder)")
    args = ap.parse_args()

    folder = Path(args.run_folder)
    brief_file = folder / "executive_brief.json"
    if not brief_file.exists():
        print(f"No executive_brief.json in {folder}. Run the agent team first.")
        return 1
    brief = json.loads(brief_file.read_text(encoding="utf-8"))
    slug = re.sub(r"[^a-z0-9]+", "-", brief.get("company_name", "startup").lower()).strip("-")[:40]
    out = Path(args.out) if args.out else folder / f"{slug}_executive_brief.pdf"
    images = {"chart": folder / "revenue_projections.png", "risk_chart": folder / "risk_profile.png"}
    print("Wrote", build_executive_pdf(out, brief, images))
    return 0


if __name__ == "__main__":
    sys.exit(main())
