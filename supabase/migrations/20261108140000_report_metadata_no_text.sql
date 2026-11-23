-- 글자가 그림으로만 들어 있어 뽑을 수 없는 PDF(OCR 필요)를 no_text로 구분한다
alter table public.report_metadata drop constraint report_metadata_chunk_status_check;
alter table public.report_metadata add constraint report_metadata_chunk_status_check
    check (chunk_status in ('pending', 'chunked', 'failed', 'no_pdf', 'no_text'));
