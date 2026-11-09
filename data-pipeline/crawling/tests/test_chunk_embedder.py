from datetime import date

import pytest

from crawling.chunk_embedder import DIMENSION, embedding_input, vector_literal


def test_embedding_input_matches_chunker_prefix():
    chunk = {
        "ticker": "000660", "company": "SK하이닉스", "broker": "유진투자증권",
        "published_at": date(2026, 10, 29), "section_title": "실적 리뷰", "body": "3분기 영업이익은 컨센서스를 상회했다.",
    }

    assert embedding_input(chunk) == (
        "[SK하이닉스(000660) | 유진투자증권 | 2026-10-29 | 실적 리뷰]\n3분기 영업이익은 컨센서스를 상회했다."
    )


def test_vector_literal_checks_dimension():
    assert vector_literal([0.5] * DIMENSION).startswith("[0.5,0.5,")
    with pytest.raises(ValueError):
        vector_literal([0.5] * 4096)
