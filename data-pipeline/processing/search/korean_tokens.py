"""BM25 검색용 한국어 형태소 자르기 (Kiwi).

적재할 때 청크를, 검색할 때 질문을 같은 함수로 자른다.
- 남기는 것: 명사(일반·고유), 영문, 숫자(2자리 이상), 한자, 어근
- 버리는 것: 조사·어미·접사·문장부호 ("하이닉스는/의/가" → "하이닉스")
- 띄어쓰기 없이 붙은 조각은 이어 붙인 말도 넣는다 ("영업"+"이익" → "영업이익", "HBM"+"4" → "hbm4", "3Q26")
"""

from __future__ import annotations

from functools import lru_cache

KEEP_TAGS = {"NNG", "NNP", "SL", "SN", "SH", "XR"}
MIN_NUMBER_CHARS = 2
# 이어 붙이는 조각 수 상한 (영업+이익+률 정도)
MAX_COMPOUND = 3


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi

    return Kiwi()


def terms(text: str) -> list[str]:
    """글을 검색어 목록으로. 같은 말이 여러 번 나오면 그만큼 들어간다(BM25 단어 빈도)."""
    if not text or not text.strip():
        return []
    result: list[str] = []
    run: list = []  # 띄어쓰기 없이 이어진 남길 조각들
    for token in _kiwi().tokenize(text):
        if token.tag not in KEEP_TAGS:
            _flush(run, result)
            run = []
            continue
        if run and token.start != run[-1].start + run[-1].len:
            _flush(run, result)
            run = []
        # 한 자리 숫자는 혼자서는 뜻이 없어 빼지만, 붙은 말(HBM4, 3Q26)에는 쓴다
        if token.tag != "SN" or len(token.form) >= MIN_NUMBER_CHARS:
            result.append(token.form.lower())
        run.append(token)
    _flush(run, result)
    return result


def _flush(run: list, result: list[str]) -> None:
    for size in range(2, min(len(run), MAX_COMPOUND) + 1):
        for start in range(len(run) - size + 1):
            result.append("".join(token.form for token in run[start : start + size]).lower())


def tsvector_literal(words: list[str]) -> str:
    """검색어 목록 → tsvector 글자 표현 ("'말':1,5 '다른말':2"). Postgres가 다시 자르지 않는다."""
    positions: dict[str, list[int]] = {}
    for position, word in enumerate(words, start=1):
        positions.setdefault(word, []).append(min(position, 16383))
    return " ".join(
        "'" + word.replace("\\", "\\\\").replace("'", "''") + "':" + ",".join(map(str, spots))
        for word, spots in positions.items()
    )


def chunk_search_text(chunk: dict) -> str:
    """청크에서 BM25 색인에 넣을 글. 회사·증권사·리포트 제목·소제목도 함께 넣어 이름으로도 찾게 한다."""
    parts = [chunk.get("company"), chunk.get("broker"), chunk.get("title"), chunk.get("section_title"), chunk.get("body")]
    return "\n".join(part for part in parts if part)


def chunk_search_columns(chunk: dict) -> dict:
    """document_chunks의 search_tokens, search_token_count 값."""
    words = terms(chunk_search_text(chunk))
    return {"search_tokens": tsvector_literal(words), "search_token_count": len(words)}
