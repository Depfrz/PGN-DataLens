alter table documents
  add column if not exists last_ocr_run_id uuid,
  add column if not exists last_ocr_processed_at timestamptz;

alter table materials
  add column if not exists data_source text not null default 'manual',
  add column if not exists verification_status text not null default 'draft',
  add column if not exists needs_review boolean not null default false,
  add column if not exists ocr_run_id uuid,
  add column if not exists ocr_extraction_id uuid,
  add column if not exists verified_by uuid,
  add column if not exists verified_at timestamptz;

create table if not exists ocr_runs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  project_id uuid not null,
  document_id uuid not null,
  engine_name text not null default 'tesseract',
  engine_version text,
  processed_at timestamptz not null default now(),
  input_file_kind text,
  input_filename text,
  input_storage_path text,
  created_at timestamptz not null default now()
);

create table if not exists ocr_item_extractions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  project_id uuid not null,
  document_id uuid not null,
  ocr_run_id uuid not null,
  page_index int,
  line_no int,
  raw_payload jsonb,
  normalized_fields jsonb,
  confidence jsonb,
  flags jsonb,
  created_at timestamptz not null default now()
);

create table if not exists item_revisions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  project_id uuid not null,
  document_id uuid,
  material_id uuid,
  change_source text not null,
  before jsonb,
  after jsonb,
  ocr_run_id uuid,
  ocr_extraction_id uuid,
  changed_by uuid,
  changed_at timestamptz not null default now()
);

create table if not exists review_decisions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  project_id uuid not null,
  document_id uuid,
  material_id uuid,
  ocr_extraction_id uuid,
  decision text not null,
  notes text,
  decided_by uuid,
  decided_at timestamptz not null default now()
);

create index if not exists ocr_runs_document_id_idx on ocr_runs(document_id);
create index if not exists ocr_runs_project_id_idx on ocr_runs(project_id);
create index if not exists ocr_item_extractions_run_id_idx on ocr_item_extractions(ocr_run_id);
create index if not exists ocr_item_extractions_document_id_idx on ocr_item_extractions(document_id);
create index if not exists item_revisions_material_id_idx on item_revisions(material_id);
create index if not exists item_revisions_document_id_idx on item_revisions(document_id);
create index if not exists review_decisions_material_id_idx on review_decisions(material_id);
create index if not exists review_decisions_document_id_idx on review_decisions(document_id);

alter table ocr_runs enable row level security;
alter table ocr_item_extractions enable row level security;
alter table item_revisions enable row level security;
alter table review_decisions enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'ocr_runs' and policyname = 'ocr_runs_owner_select'
  ) then
    create policy ocr_runs_owner_select on ocr_runs for select to authenticated using (owner_id = auth.uid());
    create policy ocr_runs_owner_insert on ocr_runs for insert to authenticated with check (owner_id = auth.uid());
    create policy ocr_runs_owner_update on ocr_runs for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy ocr_runs_owner_delete on ocr_runs for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'ocr_item_extractions' and policyname = 'ocr_item_extractions_owner_select'
  ) then
    create policy ocr_item_extractions_owner_select on ocr_item_extractions for select to authenticated using (owner_id = auth.uid());
    create policy ocr_item_extractions_owner_insert on ocr_item_extractions for insert to authenticated with check (owner_id = auth.uid());
    create policy ocr_item_extractions_owner_update on ocr_item_extractions for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy ocr_item_extractions_owner_delete on ocr_item_extractions for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'item_revisions' and policyname = 'item_revisions_owner_select'
  ) then
    create policy item_revisions_owner_select on item_revisions for select to authenticated using (owner_id = auth.uid());
    create policy item_revisions_owner_insert on item_revisions for insert to authenticated with check (owner_id = auth.uid());
    create policy item_revisions_owner_update on item_revisions for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy item_revisions_owner_delete on item_revisions for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'review_decisions' and policyname = 'review_decisions_owner_select'
  ) then
    create policy review_decisions_owner_select on review_decisions for select to authenticated using (owner_id = auth.uid());
    create policy review_decisions_owner_insert on review_decisions for insert to authenticated with check (owner_id = auth.uid());
    create policy review_decisions_owner_update on review_decisions for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy review_decisions_owner_delete on review_decisions for delete to authenticated using (owner_id = auth.uid());
  end if;
end$$;

grant select on ocr_runs, ocr_item_extractions, item_revisions, review_decisions to anon;
grant all privileges on ocr_runs, ocr_item_extractions, item_revisions, review_decisions to authenticated;

