DOCUMENT_TYPE_CODES = {
    "report":        "리서치 보고서",
    "news":          "뉴스/RSS",
    "disclosure":    "공시",
    "macro_summary": "매크로 지표 자연어 요약문",
}

VALID_DOCUMENT_TYPES = set(DOCUMENT_TYPE_CODES.keys())


def validate_document_type(document_type: str) -> bool:
    return document_type in VALID_DOCUMENT_TYPES
