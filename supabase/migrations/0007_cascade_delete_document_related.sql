delete from public.review_decisions rd
where (rd.material_id is not null and not exists (select 1 from public.materials m where m.id = rd.material_id))
   or (rd.document_id is not null and not exists (select 1 from public.documents d where d.id = rd.document_id));

delete from public.item_revisions ir
where (ir.material_id is not null and not exists (select 1 from public.materials m where m.id = ir.material_id))
   or (ir.document_id is not null and not exists (select 1 from public.documents d where d.id = ir.document_id));

delete from public.ocr_item_extractions oie
where not exists (select 1 from public.documents d where d.id = oie.document_id)
   or not exists (select 1 from public.ocr_runs r where r.id = oie.ocr_run_id);

delete from public.ocr_runs r
where not exists (select 1 from public.documents d where d.id = r.document_id);

delete from public.extraction_runs er
where not exists (select 1 from public.documents d where d.id = er.document_id);

delete from public.materials m
where m.document_id is not null
  and not exists (select 1 from public.documents d where d.id = m.document_id);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'materials_document_id_fkey') then
    alter table public.materials
      add constraint materials_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'extraction_runs_document_id_fkey') then
    alter table public.extraction_runs
      add constraint extraction_runs_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'ocr_runs_document_id_fkey') then
    alter table public.ocr_runs
      add constraint ocr_runs_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'ocr_item_extractions_document_id_fkey') then
    alter table public.ocr_item_extractions
      add constraint ocr_item_extractions_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'item_revisions_document_id_fkey') then
    alter table public.item_revisions
      add constraint item_revisions_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'review_decisions_document_id_fkey') then
    alter table public.review_decisions
      add constraint review_decisions_document_id_fkey
      foreign key (document_id) references public.documents(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'item_revisions_material_id_fkey') then
    alter table public.item_revisions
      add constraint item_revisions_material_id_fkey
      foreign key (material_id) references public.materials(id)
      on delete cascade;
  end if;

  if not exists (select 1 from pg_constraint where conname = 'review_decisions_material_id_fkey') then
    alter table public.review_decisions
      add constraint review_decisions_material_id_fkey
      foreign key (material_id) references public.materials(id)
      on delete cascade;
  end if;
end$$;

