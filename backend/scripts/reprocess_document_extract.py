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
    build_extracted_json,
    detect_upload_kind,
    extract_pdf_text,
    ocr_pdf_text,
    parse_doc_info,
    parse_materials,
    parse_materials_from_pdf_bytes,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: py -3.12 backend/scripts/reprocess_document_extract.py <document_id>")
        return 2

    document_id = sys.argv[1].strip().removesuffix(".pdf")
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    svc = create_client(settings.supabase_url, settings.supabase_service_role_key)
    doc_res = svc.table("documents").select("*").eq("id", document_id).limit(1).execute()
    d = (doc_res.data or [None])[0]
    if not d:
        print("not found")
        return 1

    user_id = d["owner_id"]
    project_id = d["project_id"]
    storage_path = d["storage_path"]

    storage = svc.storage.from_(settings.supabase_bucket)
    signed = storage.create_signed_url(storage_path, 300)
    url = signed.get("signedURL")
    if not url:
        raise RuntimeError("signedURL kosong")

    r = httpx.get(url, timeout=60.0)
    r.raise_for_status()
    file_bytes = r.content

    kind = detect_upload_kind(file_bytes, filename=str(d.get("filename") or ""), content_type=str(d.get("mime_type") or "") or None)
    if kind != "pdf":
        print("not a pdf")
        return 1

    svc.table("documents").update({"status": "extracting"}).eq("id", document_id).execute()

    text = extract_pdf_text(file_bytes)
    method = "pdf_text"
    notes: str | None = None

    if len(text.strip()) < 200:
        ocr_text, ocr_note = ocr_pdf_text(file_bytes)
        if ocr_text.strip():
            text = ocr_text
            method = "pdf_text_then_ocr"
            notes = ocr_note
        else:
            method = "pdf_text_then_ocr"
            notes = ocr_note or "OCR tidak menghasilkan teks"

    extracted_json = build_extracted_json(text, method=method, notes=notes)
    info = parse_doc_info(text)

    mats, parse_warnings = parse_materials_from_pdf_bytes(file_bytes, max_rows=5000)
    parser_used = "pdf_words_table" if mats else "text_lines"
    if not mats and len(text.strip()) >= 10:
        mats = parse_materials(text, max_rows=5000)
        parse_warnings = []

    success = len(text.strip()) >= 10 or bool(mats)

    if parse_warnings:
        extra_notes = "\n".join(parse_warnings[:50])
        notes = (notes + "\n" + extra_notes) if notes else extra_notes

    extracted_json["materials_preview"] = mats[:20]
    extracted_json["materials_parser"] = parser_used
    if parse_warnings:
        extracted_json["warnings"] = parse_warnings[:50]

    svc.table("documents").update(
        {
            "document_type": info.document_type,
            "document_number": info.document_number,
            "status": "success" if success else "failed",
        }
    ).eq("id", document_id).execute()

    inserted = 0
    if mats:
        svc.table("materials").delete().eq("document_id", document_id).eq("owner_id", user_id).execute()
        to_insert = []
        from uuid import uuid4
        from datetime import datetime

        for m in mats:
            to_insert.append(
                {
                    "id": str(uuid4()),
                    "owner_id": user_id,
                    "project_id": project_id,
                    "document_id": document_id,
                    "description": m.get("description") or "",
                    "size": m.get("size"),
                    "quantity": m.get("quantity"),
                    "unit": m.get("unit"),
                    "heat_no": None,
                    "tag_no": None,
                    "spec": m.get("spec"),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
        ins = svc.table("materials").insert(to_insert).execute()
        inserted = len(ins.data or [])

    from uuid import uuid4
    from datetime import datetime

    run_id = str(uuid4())
    svc.table("extraction_runs").insert(
        {
            "id": run_id,
            "owner_id": user_id,
            "document_id": document_id,
            "method": method,
            "status": "success" if success else "failed",
            "extracted_json": extracted_json,
            "notes": notes,
            "created_at": datetime.utcnow().isoformat(),
        }
    ).execute()

    print("done", {"success": success, "inserted": inserted, "method": method})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
