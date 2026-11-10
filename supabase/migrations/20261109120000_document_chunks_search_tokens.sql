-- 한국어 형태소 BM25 검색용 색인.
-- Postgres 기본 전문검색은 한국어 조사를 떼지 못해서, 적재할 때 Kiwi로 형태소를 잘라 직접 넣는다.
-- search_tokens는 "'형태소':위치,..." 형태로 넣어 Postgres가 다시 자르지 않게 하고,
-- 위치 개수(단어 빈도)와 search_token_count(문서 길이)로 BM25 점수를 계산한다.
alter table public.document_chunks add column search_tokens tsvector;
alter table public.document_chunks add column search_token_count integer;

create index document_chunks_search_tokens_idx on public.document_chunks using gin (search_tokens);
