import sqlite3
from pathlib import Path

from functions.get_target_price_data import get_target_price_data
from functions.search_documents import search_documents


class FakeEmbeddingModel:
    def embed(self, text):
        return [0.1, 0.2]


class FakeVectorDB:
    def search(self, query_vector, top_k=5, filter=None):
        return [
            {
                "id": "KIRS_005930_001_chunk_001",
                "content": "HBM 수요 증가가 성장 요인이다.",
                "score": 0.91,
                "metadata": {
                    "chunk_id": "KIRS_005930_001_chunk_001",
                    "ticker": "005930",
                    "company": "삼성전자",
                    "date": "2026-06-15",
                    "source": "KIRS",
                    "author_org": "테스트증권",
                    "document_type": "report",
                    "report_type": "company_report",
                    "title": "삼성전자 리포트",
                    "page_start": 3,
                    "page_end": 4,
                    "url": "https://example.com/report.pdf",
                },
            }
        ]


class FakeRelationalDB:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)


def test_search_documents_returns_evidence_fields():
    result = search_documents(
        query="HBM",
        ticker="005930",
        embedding_model=FakeEmbeddingModel(),
        vector_db=FakeVectorDB(),
    )

    item = result["results"][0]
    assert item["report_id"] == "KIRS_005930_001"
    assert item["author_org"] == "테스트증권"
    assert item["page_start"] == 3
    assert item["page_end"] == 4


def test_get_target_price_data_returns_company_and_title(tmp_path):
    db_path = tmp_path / "reports.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE report_metadata (
            report_id TEXT PRIMARY KEY,
            ticker TEXT,
            company TEXT,
            title TEXT,
            original_url TEXT,
            pdf_url TEXT
        );
        CREATE TABLE target_price_data (
            report_id TEXT,
            ticker TEXT,
            published_at TEXT,
            source TEXT,
            author_org TEXT,
            target_price INTEGER,
            investment_opinion TEXT,
            report_type TEXT
        );
        INSERT INTO report_metadata VALUES (
            'R1', '005930', '삼성전자', '삼성전자 기업분석', 'https://example.com', 'https://example.com/a.pdf'
        );
        INSERT INTO target_price_data VALUES (
            'R1', '005930', '2026-06-15', 'KIRS', '테스트증권', 95000, '매수', 'company_report'
        );
        """
    )
    conn.commit()
    conn.close()

    result = get_target_price_data(
        ticker="005930",
        relational_db=FakeRelationalDB(db_path),
    )

    assert result["company"] == "삼성전자"
    assert result["target_prices"][0]["title"] == "삼성전자 기업분석"
    assert result["summary"]["avg_target_price"] == 95000
