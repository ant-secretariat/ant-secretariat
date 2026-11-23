-- 문서 검색 평가용 골든셋 (기획서 v2 7-1절). 질문과 정답 청크 ID만 두고 리포트 본문은 저장하지 않는다.
-- 평가는 snapshot_tag로 고정한 묶음을 기준으로 하고, 사람이 검토하지 않은 행(reviewed=false)은 따로 집계할 수 있다.
create table public.search_golden_set (
    golden_id           text primary key,              -- G01, G02 ...
    snapshot_tag        text not null,                 -- 평가 묶음 (예: 2026-11-09-v1)
    query               text not null,
    ticker              text,                          -- 비우면 전 종목 검색
    as_of               date,                          -- 이날까지 게시된 문서만 대상 (과거 시점 문항)
    question_type       text not null check (question_type in
                        ('single_number', 'reason', 'latest_opinion', 'point_in_time', 'broker_compare', 'change')),
    agenda_id           text,                          -- 토론 아젠다와 연결할 때 (valuation, risk ...)
    answer_source       text,                          -- body / table / chart
    expected_chunk_ids  text[] not null default '{}',  -- document_chunks.chunk_id
    expected_doc_ids    text[] not null default '{}',  -- 정답 청크가 속한 리포트
    labeled_by          text not null,                 -- 라벨링한 사람 (수경, claude 등)
    reviewed            boolean not null default false, -- 사람이 정답을 확인했는지
    is_active           boolean not null default true,
    note                text,
    created_at          timestamptz not null default now()
);

create index search_golden_set_snapshot_idx on public.search_golden_set (snapshot_tag) where is_active;

alter table public.search_golden_set enable row level security;
