"""precheck — 관문2·3 사전 판정. 설정 로더만 먼저 제공하고, 엔진은 다음 PR에서 추가한다."""
from agents.debate_renewal.precheck.config import PrecheckConfig, load_default_config

__all__ = ["PrecheckConfig", "load_default_config"]
