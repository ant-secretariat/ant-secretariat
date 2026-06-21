DOCUMENT_TYPE_CODES = {
    "report":         "리서치 보고서",
    "news":           "뉴스/RSS",
    "disclosure":     "공시",
    "macro_summary":  "매크로 지표 자연어 요약문",
}

VALID_DOCUMENT_TYPES = set(DOCUMENT_TYPE_CODES.keys())


REPORT_TYPE_CODES = {
    "company_report":    "기업 분석 리포트",
    "issue_comment":     "이슈 코멘트",
    "industry_report":   "산업 리포트",
    "technical_report":  "기술분석 리포트",
    "ai_company_report": "AI 기업분석 리포트",
    "unknown":           "분류 실패",
}

VALID_REPORT_TYPES = set(REPORT_TYPE_CODES.keys())


def validate_document_type(document_type: str) -> bool:
    return document_type in VALID_DOCUMENT_TYPES


def validate_report_type(report_type: str) -> bool:
    return report_type in VALID_REPORT_TYPES
