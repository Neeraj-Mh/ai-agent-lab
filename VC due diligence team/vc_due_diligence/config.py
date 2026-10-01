"""Central configuration: pick the LLM provider (Gemini or Claude) and models via environment variables.

    LLM_PROVIDER = gemini | claude          (default: gemini)
    FAST_MODEL   = model for lighter steps   (intake, report, infographic, research)
    DEEP_MODEL   = model for heavy reasoning (financials, risk, investment memo)
    SEARCH_BACKEND = auto | google | tavily | duckduckgo
    IMAGE_PROVIDER = auto | gemini | local
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

# Load .env from the project folder (works for both `python run.py` and `adk web`).
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PACKAGE_DIR / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
if PROVIDER in {"anthropic", "claude"}:
    PROVIDER = "claude"
elif PROVIDER not in {"gemini", "google"}:
    raise ValueError(f"Unsupported LLM_PROVIDER '{PROVIDER}'. Use 'gemini' or 'claude'.")
else:
    PROVIDER = "gemini"

DEFAULT_MODELS = {
    "gemini": {"fast": "gemini-3.5-flash", "deep": "gemini-3.1-pro-preview"},
    "claude": {"fast": "claude-sonnet-5-5", "deep": "claude-opus-5-5"},
}

FAST_MODEL_NAME = os.getenv("FAST_MODEL") or DEFAULT_MODELS[PROVIDER]["fast"]
DEEP_MODEL_NAME = os.getenv("DEEP_MODEL") or DEFAULT_MODELS[PROVIDER]["deep"]

GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")

_search = os.getenv("SEARCH_BACKEND", "auto").strip().lower()
if _search == "auto":
    if PROVIDER == "gemini":
        _search = "google"
    elif os.getenv("TAVILY_API_KEY"):
        _search = "tavily"
    else:
        _search = "duckduckgo"
if _search == "google" and PROVIDER != "gemini":
    # Google Search grounding is a Gemini-only built-in tool.
    _search = "tavily" if os.getenv("TAVILY_API_KEY") else "duckduckgo"
SEARCH_BACKEND = _search

_image = os.getenv("IMAGE_PROVIDER", "auto").strip().lower()
if _image == "auto":
    _image = "gemini" if os.getenv("GOOGLE_API_KEY") else "local"
IMAGE_PROVIDER = _image

OUTPUT_ROOT = Path(os.getenv("OUTPUT_DIR", PROJECT_DIR / "outputs")).resolve()


def build_model(tier: str):
    """Return something ADK's LlmAgent accepts as `model` for the chosen provider and tier."""
    name = FAST_MODEL_NAME if tier == "fast" else DEEP_MODEL_NAME
    if PROVIDER == "gemini":
        return name  # ADK talks to Gemini natively with a plain model string.

    # Claude runs through ADK's LiteLLM bridge.
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise EnvironmentError("LLM_PROVIDER=claude needs ANTHROPIC_API_KEY in your .env")
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(model=name if name.startswith("anthropic/") else f"anthropic/{name}")


def describe() -> str:
    return (
        f"provider={PROVIDER} | fast={FAST_MODEL_NAME} | deep={DEEP_MODEL_NAME} | "
        f"search={SEARCH_BACKEND} | infographic={IMAGE_PROVIDER}"
    )
