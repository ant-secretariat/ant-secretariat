"""키워드 사전·intent_data_sources.json 로더.

두 JSON은 프로세스 시작 시 1회 로드한다 (기획서 1.3). 테스트나 실험에서는
PrecheckConfig를 직접 만들어 precheck()에 주입할 수 있다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

from agents.debate_renewal.contracts import AgendaId


@dataclass(frozen=True)
class AgendaKeywords:
    active: bool
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class AgendaSource:
    requires_any: tuple[str, ...]
    stale_after_days: int
    t0_available: bool


@dataclass(frozen=True)
class PrecheckConfig:
    keyword_version: str
    source_version: str
    default_agendas: tuple[AgendaId, ...]
    max_agendas: int
    keywords: dict[AgendaId, AgendaKeywords]
    shareholder_return_replaces: tuple[AgendaId, ...]
    growth_replaces: tuple[AgendaId, ...]
    generic_keywords: tuple[str, ...]
    advice_keywords: tuple[str, ...]
    sources: dict[AgendaId, AgendaSource]
    # 명백한 범위 밖 단어. 아젠다·일반 키워드가 함께 걸려도 거절한다 (일반 단어 "어때" 등의 오탐 방지)
    out_of_scope_keywords: tuple[str, ...] = ()
    # 단독으로는 범위 판정 근거가 약한 단어(추천 등). 질의에 종목명이 있어야 통과한다
    weak_signal_keywords: tuple[str, ...] = ()

    @property
    def dictionary_version(self) -> str:
        return f"{self.keyword_version}+{self.source_version}"


def normalize(text: str) -> str:
    """소문자 + 모든 공백 제거. 한글 키워드의 띄어쓰기 차이를 흡수한다."""
    return "".join(text.lower().split())


def _ids(values: list[str]) -> tuple[AgendaId, ...]:
    return tuple(AgendaId(v) for v in values)


def _norm_all(values: list[str]) -> tuple[str, ...]:
    return tuple(normalize(v) for v in values)


def build_config(keyword_doc: dict, source_doc: dict) -> PrecheckConfig:
    kw = {
        AgendaId(k): AgendaKeywords(bool(v["active"]), _norm_all(v["keywords"]))
        for k, v in keyword_doc["agendas"].items()
    }
    src = {
        AgendaId(k): AgendaSource(
            tuple(v["requires_any"]), int(v["stale_after_days"]), bool(v["t0_available"])
        )
        for k, v in source_doc["agendas"].items()
    }
    missing = set(AgendaId) - set(kw) | set(AgendaId) - set(src)
    if missing:
        raise ValueError(f"사전에 없는 아젠다: {sorted(m.value for m in missing)}")
    rules = keyword_doc["selection_rules"]
    return PrecheckConfig(
        keyword_version=keyword_doc["version"],
        source_version=source_doc["version"],
        default_agendas=_ids(keyword_doc["default_agendas"]),
        max_agendas=int(keyword_doc["max_agendas"]),
        keywords=kw,
        shareholder_return_replaces=_ids(rules["shareholder_return_replaces"]),
        growth_replaces=_ids(rules["growth_replaces"]),
        generic_keywords=_norm_all(keyword_doc["generic_keywords"]),
        advice_keywords=_norm_all(keyword_doc["investment_advice_keywords"]),
        sources=src,
        out_of_scope_keywords=_norm_all(keyword_doc.get("out_of_scope_keywords", [])),
        weak_signal_keywords=_norm_all(keyword_doc.get("weak_signal_keywords", [])),
    )


def _read(name: str, base: Path | None) -> dict:
    if base is not None:
        return json.loads((base / name).read_text(encoding="utf-8"))
    ref = resources.files("agents.debate_renewal").joinpath("data", name)
    return json.loads(ref.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_default_config() -> PrecheckConfig:
    return build_config(_read("keyword_dictionary.json", None), _read("intent_data_sources.json", None))


def load_config_from(directory: Path) -> PrecheckConfig:
    return build_config(_read("keyword_dictionary.json", directory), _read("intent_data_sources.json", directory))
