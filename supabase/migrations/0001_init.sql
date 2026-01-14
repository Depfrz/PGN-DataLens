create extension if not exists pgcrypto;

create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  name text not null,
  location text,
  year int,
  status text,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  owner_id uuid not null,
  storage_path text not null,
  filename text not null,
  document_type text not null default 'Lainnya',
  document_number text,
  document_date date,
  status text not null default 'uploaded',
  uploaded_at timestamptz not null default now()
);

create table if not exists materials (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  project_id uuid not null,
  document_id uuid,
  description text not null,
  size text,
  quantity double precision,
  unit text,
  heat_no text,
  tag_no text,
  spec text,
  created_at timestamptz not null default now()
);

create table if not exists extraction_runs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  document_id uuid not null,
  method text not null,
  status text not null,
  extracted_json jsonb,
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists documents_project_id_idx on documents(project_id);
create index if not exists materials_project_id_idx on materials(project_id);
create index if not exists materials_document_id_idx on materials(document_id);
create index if not exists projects_owner_id_idx on projects(owner_id);
create index if not exists documents_owner_id_idx on documents(owner_id);
create index if not exists materials_owner_id_idx on materials(owner_id);
create index if not exists extraction_runs_owner_id_idx on extraction_runs(owner_id);

alter table projects enable row level security;
alter table documents enable row level security;
alter table materials enable row level security;
alter table extraction_runs enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'projects' and policyname = 'projects_owner_select'
  ) then
    create policy projects_owner_select on projects for select to authenticated using (owner_id = auth.uid());
    create policy projects_owner_insert on projects for insert to authenticated with check (owner_id = auth.uid());
    create policy projects_owner_update on projects for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy projects_owner_delete on projects for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'documents' and policyname = 'documents_owner_select'
  ) then
    create policy documents_owner_select on documents for select to authenticated using (owner_id = auth.uid());
    create policy documents_owner_insert on documents for insert to authenticated with check (owner_id = auth.uid());
    create policy documents_owner_update on documents for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy documents_owner_delete on documents for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'materials' and policyname = 'materials_owner_select'
  ) then
    create policy materials_owner_select on materials for select to authenticated using (owner_id = auth.uid());
    create policy materials_owner_insert on materials for insert to authenticated with check (owner_id = auth.uid());
    create policy materials_owner_update on materials for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy materials_owner_delete on materials for delete to authenticated using (owner_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'extraction_runs' and policyname = 'extraction_runs_owner_select'
  ) then
    create policy extraction_runs_owner_select on extraction_runs for select to authenticated using (owner_id = auth.uid());
    create policy extraction_runs_owner_insert on extraction_runs for insert to authenticated with check (owner_id = auth.uid());
    create policy extraction_runs_owner_update on extraction_runs for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    create policy extraction_runs_owner_delete on extraction_runs for delete to authenticated using (owner_id = auth.uid());
  end if;
end$$;

grant select on projects, documents, materials, extraction_runs to anon;
grant all privileges on projects, documents, materials, extraction_runs to authenticated;

