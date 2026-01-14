alter table documents
  add column if not exists file_kind text not null default 'pdf',
  add column if not exists mime_type text,
  add column if not exists file_size_bytes bigint,
  add column if not exists image_width int,
  add column if not exists image_height int,
  add column if not exists original_filename text;

