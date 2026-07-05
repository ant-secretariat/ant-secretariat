"""InsightBoard 에이전트(Agent E) 설정."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")

InsightBoardFeature = Literal["price", "macro", "disclosure"]

MAX_COMPANIES = 3
COMMENT_MODEL = os.getenv("INSIGHT_BOARD_LLM_MODEL", "solar-pro3")
