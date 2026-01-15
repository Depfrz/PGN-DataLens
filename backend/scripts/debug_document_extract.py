from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from supabase import create_client

from backend.app_settings import settings
from backend.services.extraction import (
    detect_upload_kind,
    extract_pdf_text,
    ocr_pdf_text,
    parse_materials,
    parse_materials_from_pdf_bytes,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: py -3.12 backend/scripts/debug_document_extract.py <document_id_or_filename>")
        return 2

    needle = sys.argv[1].strip()
    doc_id = needle.removesuffix(".pdf")

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    svc = create_client(settings.supabase_url, settings.supabase_service_role_key)
    res = svc.table("documents").select("*").or_(f"id.eq.{doc_id},filename.eq.{doc_id}.pdf,filename.ilike.%{doc_id}%").execute()
    docs = res.data or []
    print("matched_docs=", len(docs))
    if not docs:
        return 1
    d = docs[0]
    print("doc.id=", d.get("id"))
    print("doc.filename=", d.get("filename"))
    print("doc.storage_path=", d.get("storage_path"))
    print("doc.status=", d.get("status"))
    print("doc.file_kind=", d.get("file_kind"))
    print("doc.mime_type=", d.get("mime_type"))

    storage = svc.storage.from_(settings.supabase_bucket)
    signed = storage.create_signed_url(d["storage_path"], 300)
    url = signed.get("signedURL")
    if not url:
        raise RuntimeError("signedURL kosong")

    r = httpx.get(url, timeout=60.0)
    print("download.status=", r.status_code)
    r.raise_for_status()
    b = r.content
    print("download.bytes=", len(b))
    print("head=", b[:10])

    try:
        kind = detect_upload_kind(b, filename=str(d.get("filename") or ""), content_type=str(d.get("mime_type") or "") or None)
        print("detected_kind=", kind)
    except Exception as e:
        print("detect_upload_kind_error=", repr(e))

    try:
        text = extract_pdf_text(b)
        print("extract_pdf_text.len=", len(text))
        print("extract_pdf_text.sample=", (text[:200] or "").replace("\n", " "))
    except Exception as e:
        print("extract_pdf_text_error=", repr(e))
        text = ""

    try:
        mats = parse_materials_from_pdf_bytes(b)
        print("parse_materials_from_pdf_bytes.rows=", len(mats))
    except Exception as e:
        print("parse_materials_from_pdf_bytes_error=", repr(e))
        mats = []

    if not mats and text:
        try:
            mats2 = parse_materials(text)
            print("parse_materials(text).rows=", len(mats2))
        except Exception as e:
            print("parse_materials(text)_error=", repr(e))

    if len(text.strip()) < 200:
        try:
            ocr_text, note = ocr_pdf_text(b)
            print("ocr_pdf_text.note=", note)
            print("ocr_pdf_text.len=", len(ocr_text))
        except Exception as e:
            print("ocr_pdf_text_error=", repr(e))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
