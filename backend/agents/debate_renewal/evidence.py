"""데이터 함수 검색 결과 → Evidence 변환.

- 입력은 `search_documents`(또는 `get_agent_context`의 `documents`)의 `results[]` 한 줄이다.
- `evidence_id`(S1, S2…)는 토론 하나 안에서 코드가 붙인다. 같은 chunk_id는 아젠다가 달라도 같은 id를 쓴다.
- 모르는 값은 None으로 둔다(빈 문자열로 채우지 않음, AGENTS.md 5).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from agents.debate_renewal.schemas import Evidence

# 프롬프트에 넣는 근거 본문 길이(글자). 임시값: 기준선 평가 후 확정(README "확정 필요")
PREVIEW_CHARS = 600
_DOCUMENT_TYPES = {"report", "news", "disclosure", "macro"}


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def to_evidence(raw: Mapping[str, Any], evidence_id: str, source: str = "original") -> Evidence:
    doc_type = raw.get("document_type")
    content = _text(raw.get("content")) or ""
    return Evidence(
        evidence_id=evidence_id,
        chunk_id=str(raw["chunk_id"]),
        document_type=doc_type if doc_type in _DOCUMENT_TYPES else "structured",
        title=_text(raw.get("title")) or "(제목 없음)",
        source=_text(raw.get("source")) or _text(raw.get("author_org")) or "알 수 없음",
        author_org=_text(raw.get("author_org")),
        date=(_text(raw.get("date")) or "")[:10],
        url=_text(raw.get("url")),
        content_preview=content[:PREVIEW_CHARS],
        evidence_source=source,
    )


class EvidencePool:
    """토론 하나의 근거 목록. 아젠다별로 넣고, chunk_id가 같으면 같은 Evidence를 돌려준다."""

    def __init__(self) -> None:
        self._by_chunk: dict[str, Evidence] = {}

    def add(self, results: Sequence[Mapping[str, Any]], source: str = "original") -> list[Evidence]:
        """source: 처음 검색은 original, 근거 부족 루프의 보완 검색은 gap_fill(이미 있는 조각은 원래 표기 유지)."""
        picked: list[Evidence] = []
        for raw in results:
            if not raw.get("chunk_id"):
                continue
            key = str(raw["chunk_id"])
            ev = self._by_chunk.get(key)
            if ev is None:
                ev = to_evidence(raw, f"S{len(self._by_chunk) + 1}", source)
                self._by_chunk[key] = ev
            if ev not in picked:
                picked.append(ev)
        return picked

    def all(self) -> list[Evidence]:
        return list(self._by_chunk.values())
