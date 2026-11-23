-- 청킹 방식을 바꿔 사라진 청크는 지우지 않고 비활성으로 남긴다.
-- 토론·트렌드 리포트 근거(Evidence.chunk_id)와 온톨로지 ISSUE가 청크 ID를 저장하므로, 링크가 끊기지 않게 한다.
-- 검색은 활성 청크만, 청크 ID로 직접 여는 근거 조회는 비활성 청크도 돌려준다.
alter table public.document_chunks add column is_active boolean not null default true;

create index document_chunks_active_ticker_published_idx
    on public.document_chunks (ticker, published_at desc) where is_active;
