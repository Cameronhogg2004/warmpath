"""Settings: where the keys come from, which model, what it costs, and the limits.

The .env file is looked for in this repo's folder first, then one folder up
(graders keep theirs in submissions/). The nearer file wins: python-dotenv
never overrides a value that is already set.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATIC = ROOT / "static"

for folder in (ROOT, ROOT.parent):
    if (folder / ".env").is_file():
        load_dotenv(folder / ".env")

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PORTKEY_API_KEY = os.environ.get("PORTKEY_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_NAME = os.environ.get("WARMPATH_MODEL", "").strip() or "gpt-6-luna"
# "low" was chosen after measuring low against medium (docs/benchmark_effort.json).
REASONING_EFFORT = os.environ.get("WARMPATH_EFFORT", "").strip() or "low"


def provider() -> str:
    """'portkey', 'openai', or '' when no key is set (the app still opens)."""
    if PORTKEY_API_KEY:
        return "portkey"
    if OPENAI_API_KEY:
        return "openai"
    return ""


# --- Prices (USD per million tokens), gpt-6-luna list prices, October 2026 ---
# Sources: eesel.ai/blog/gpt-6-luna-pricing and anotherwrapper.com/llm-pricing/gpt-6-luna.
# Reasoning tokens are billed as output. Web search is billed per call.
PRICE_INPUT = float(os.environ.get("WARMPATH_PRICE_INPUT", 0.10))
PRICE_CACHED_INPUT = float(os.environ.get("WARMPATH_PRICE_CACHED_INPUT", 0.01))
PRICE_OUTPUT = float(os.environ.get("WARMPATH_PRICE_OUTPUT", 0.50))
PRICE_WEB_SEARCH_CALL = 10.0 / 1000  # $10 per 1,000 calls


def cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int, web_searches: int = 0) -> float:
    """Dollar cost of one model call (or a sum of them). input_tokens includes cached ones."""
    fresh = max(input_tokens - cached_tokens, 0)
    return (fresh * PRICE_INPUT + cached_tokens * PRICE_CACHED_INPUT
            + output_tokens * PRICE_OUTPUT) / 1e6 + web_searches * PRICE_WEB_SEARCH_CALL


# --- Limits ------------------------------------------------------------------------
DAILY_BUDGET_USD = float(os.environ.get("WARMPATH_DAILY_BUDGET_USD", 2.00))
RUN_TIMEOUT_S = 240
RUNS_PER_MINUTE = 6
MAX_OUTPUT_TOKENS = 6000           # per model response, reasoning included
SCOUT_REQUEST_LIMIT = 14           # model calls in one scout run
SCOUT_TOOL_CALLS_LIMIT = 16        # tool calls in one scout run
SCOUT_TOTAL_TOKENS_LIMIT = 120_000
PER_TOOL_CALL_LIMIT = 6            # calls to any single tool in one run
WEB_SEARCH_MAX_USES = 3
RECENT_YEARS = 3                   # a tie counts as current if it is this recent


def current_year() -> int:
    return date.today().year
