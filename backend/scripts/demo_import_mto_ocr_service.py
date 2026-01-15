from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import httpx
from supabase import create_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app_settings import settings
from backend.main import _mto_row_to_material_fields, _tesseract_engine_version, _utc_now_iso
from backend.services.extraction import (
    detect_upload_kind,
    extract_mto_from_image_bytes_advanced,
    extract_mto_from_pdf_bytes_advanced,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: py -3.12 backend/scripts/demo_import_mto_ocr_service.py <document_id>")
        return 2

    document_id = sys.argv[1].strip().removesuffix(".pdf").removesuffix(".png")
    svc = create_client(settings.supabase_url, settings.supabase_service_role_key)
    doc_res = svc.table("documents").select("*").eq("id", document_id).limit(1).execute()
    doc = (doc_res.data or [None])[0]
    if not doc:
        print("not found")
        return 1

    storage = svc.storage.from_(settings.supabase_bucket)
    signed = storage.create_signed_url(doc["storage_path"], 300)
    url = signed.get("signedURL")
    if not url:
        raise RuntimeError("signedURL kosong")

    r = httpx.get(url, timeout=60.0)
    r.raise_for_status()
    raw = r.content

    kind = detect_upload_kind(raw, filename=str(doc.get("filename") or ""), content_type=str(doc.get("mime_type") or "") or None)
    page_index = 0
    if doc.get("file_kind") == "image" or kind == "image":
        rows = extract_mto_from_image_bytes_advanced(raw)
    else:
        rows = extract_mto_from_pdf_bytes_advanced(raw, page_index)

    run_id = str(uuid4())
    now = _utc_now_iso()
    run_row = {
        "id": run_id,
        "owner_id": doc["owner_id"],
        "project_id": doc["project_id"],
        "document_id": doc["id"],
        "engine_name": "tesseract",
        "engine_version": _tesseract_engine_version(),
        "processed_at": now,
        "input_file_kind": doc.get("file_kind"),
        "input_filename": doc.get("filename"),
        "input_storage_path": doc.get("storage_path"),
        "created_at": now,
    }
    svc.table("ocr_runs").insert(run_row).execute()
    svc.table("documents").update({"last_ocr_run_id": run_id, "last_ocr_processed_at": now}).eq("id", doc["id"]).execute()
    svc.table("materials").delete().eq("document_id", doc["id"]).eq("owner_id", doc["owner_id"]).eq("data_source", "ocr").execute()

    extractions = []
    mats = []
    flagged = 0
    for r in rows:
        norm, flags = _mto_row_to_material_fields(r)
        needs_review = len(flags) > 0
        if needs_review:
            flagged += 1
        ext_id = str(uuid4())
        extractions.append(
            {
                "id": ext_id,
                "owner_id": doc["owner_id"],
                "project_id": doc["project_id"],
                "document_id": doc["id"],
                "ocr_run_id": run_id,
                "page_index": page_index,
                "line_no": int(r.get("item") or 0) if str(r.get("item") or "").isdigit() else None,
                "raw_payload": r,
                "normalized_fields": norm,
                "confidence": None,
                "flags": {"flags": flags, "needs_review": needs_review},
                "created_at": now,
            }
        )
        mats.append(
            {
                "id": str(uuid4()),
                "owner_id": doc["owner_id"],
                "project_id": doc["project_id"],
                "document_id": doc["id"],
                "description": norm.get("description") or "",
                "spec": norm.get("spec"),
                "size": norm.get("size"),
                "quantity": norm.get("quantity"),
                "unit": norm.get("unit"),
                "created_at": now,
                "data_source": "ocr",
                "verification_status": "needs_review" if needs_review else "draft",
                "needs_review": needs_review,
                "ocr_run_id": run_id,
                "ocr_extraction_id": ext_id,
            }
        )

    svc.table("ocr_item_extractions").insert(extractions).execute()
    ins = svc.table("materials").insert(mats).execute()
    print({"run_id": run_id, "rows": len(rows), "inserted": len(ins.data or []), "flagged": flagged})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
