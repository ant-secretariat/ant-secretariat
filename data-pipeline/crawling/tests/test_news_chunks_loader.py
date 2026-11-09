from datetime import date

from crawling.news_chunks_loader import names_for, news_chunk_rows, news_id, press_allowed, select_articles


def test_names_and_press_rules():
    query, names = names_for("035420", "NAVER", ["NAVER"])
    assert query == "네이버" and "NAVER" in names
    assert press_allowed("hankyung.com") and press_allowed("biz.chosun.com") and press_allowed("news.mt.co.kr")
    assert not press_allowed("topstarnews.net") and not press_allowed("fakehankyung.com")
    assert news_id("https://a.com/1") == news_id("https://a.com/1") != news_id("https://a.com/2")


def test_select_articles_needs_company_in_title_and_allowed_press():
    rows = [
        {"title": "LG이노텍, 기판 증설", "press": "hankyung.com"},
        {"title": "LG이노텍, 기판 증설", "press": "topstarnews.net"},
        {"title": "애플 신제품 출시", "press": "hankyung.com"},
    ]

    assert select_articles(rows, ["LG이노텍"]) == [rows[0]]


def test_news_chunk_rows_split_long_articles_and_use_kst_date():
    article = {
        "news_id": "NEWS_x", "ticker": "011070", "company": "LG이노텍", "press": "hankyung.com",
        "published_at": "2026-11-08T16:30:00+00:00", "title": "LG이노텍 기판 증설", "original_url": "https://h/1",
        "mentioned_tickers": ["011070"],
    }
    rows = news_chunk_rows(article, "LG이노텍이 기판 증설을 발표했다. " * 120, "html")

    assert len(rows) >= 2 and rows[0]["document_type"] == "news"
    assert rows[0]["published_at"] == date(2026, 11, 9)  # 한국 시간 기준 날짜
    assert rows[0]["broker"] == "hankyung.com" and rows[0]["search_token_count"] > 0
    assert len({row["chunk_id"] for row in rows}) == len(rows)
