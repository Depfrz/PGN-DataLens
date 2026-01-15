begin;

truncate table
  public.review_decisions,
  public.item_revisions,
  public.ocr_item_extractions,
  public.ocr_runs,
  public.extraction_runs,
  public.materials,
  public.documents,
  public.projects
restart identity cascade;

commit;

