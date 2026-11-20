from __future__ import annotations

import os

from dotenv import load_dotenv
from phoenix.evals import LLM

load_dotenv()


def judge_llm() -> LLM:
    api_key = os.environ["USAI_API_KEY"]
    base_url = os.environ["USAI_BASE_URL"].rstrip("/") + "/api/v1"
    model = os.getenv("JUDGE_MODEL", "claude_4_6_sonnet")
    return LLM(
        provider="openai",
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
