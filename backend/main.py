from __future__ import annotations

import os
import logging
import hashlib
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .app_settings import require_supabase_anon, require_supabase_service, settings
from .db import get_supabase_anon, get_supabase_service
from .schemas import (
    AuthRequest,
    AuthSession,
    Document,
    MeResponse,
    EmailRequest,
    EmailAvailabilityResponse,
    ExtractionResponse,
    Material,
    MaterialCreate,
    MaterialListResponse,
    MaterialUpdate,
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProjectWithSummary,
)
from .services.extraction import (
    build_extracted_json,
    extract_pdf_text,
    extract_mto_from_pdf_bytes_advanced,
    extract_mto_from_image_bytes_advanced,
    convert_image_bytes_to_pdf,
    detect_upload_kind,
    ocr_pdf_text,
    parse_doc_info,
    parse_materials,
    parse_materials_from_pdf_bytes,
    validate_and_convert_image_upload,
    _try_import_pytesseract,
)


app = FastAPI(title="PGN DataLens", version="0.1.0")
security = HTTPBearer(auto_error=False)
logger = logging.getLogger("pgn_datalens")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


FRONTEND_DIR = (Path(__file__).parent.parent / "frontend").resolve()
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _require_auth(creds: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = creds.credentials
    try:
        anon = get_supabase_anon()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        user = anon.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if user is None or user.user is None or not getattr(user.user, "id", None):
        raise HTTPException(status_code=401, detail="Invalid token")
    return str(user.user.id)


def _email_fingerprint(email: str) -> str:
    norm = (email or "").strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def _email_exists(email: str) -> bool:
    svc = get_supabase_service()
    target = (email or "").strip().lower()
    page = 1
    per_page = 200
    while True:
        users = svc.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            return False
        for u in users:
            u_email = getattr(u, "email", None)
            if u_email and str(u_email).strip().lower() == target:
                return True
        if len(users) < per_page:
            return False
        page += 1


def _duplicate_email_http() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "duplicate_email",
            "message": "A user with this email address has already been registered",
            "actions": {
                "login": True,
                "password_recovery": True,
                "different_email": True,
            },
        },
    )


def _storage_file_options(content_type: str) -> dict[str, str]:
    return {"content-type": content_type}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _insert_item_revision(
    svc,
    *,
    owner_id: str,
    project_id: str,
    document_id: str | None,
    material_id: str | None,
    change_source: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    changed_by: str | None,
    ocr_run_id: str | None = None,
    ocr_extraction_id: str | None = None,
) -> None:
    row = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "project_id": project_id,
        "document_id": document_id,
        "material_id": material_id,
        "change_source": change_source,
        "before": before,
        "after": after,
        "ocr_run_id": ocr_run_id,
        "ocr_extraction_id": ocr_extraction_id,
        "changed_by": changed_by,
        "changed_at": _utc_now_iso(),
    }
    svc.table("item_revisions").insert(row).execute()


def _tesseract_engine_version() -> str | None:
    p = _try_import_pytesseract()
    if p is None:
        return None
    try:
        return str(p.get_tesseract_version())
    except Exception:
        return None


def _mto_row_to_material_fields(row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_desc = str(row.get("description") or "").strip()
    raw_mat = str(row.get("material") or "").strip()
    raw_nps = str(row.get("nps") or "").strip()
    qty = row.get("qty_value")
    unit = str(row.get("qty_unit") or "").strip()

    name = raw_desc or raw_mat
    spec_parts: list[str] = []
    if raw_mat and raw_mat != name:
        spec_parts.append(raw_mat)

    if "," in raw_desc:
        head, tail = raw_desc.split(",", 1)
        head = head.strip()
        tail = tail.strip()
        if head:
            name = head
        if tail:
            spec_parts.append(tail)

    spec = "\n".join([p for p in spec_parts if p]).strip() or None

    size = raw_nps or None
    if size and size.isdigit():
        size = f"{size} Inch"

    out = {
        "description": name or "",
        "spec": spec,
        "size": size,
        "quantity": float(qty) if qty is not None else None,
        "unit": unit or None,
    }

    flags: list[str] = []
    if not out["description"]:
        flags.append("missing_description")
    if out["quantity"] is None:
        flags.append("missing_quantity")
    if out["unit"] is None:
        flags.append("missing_unit")
    if out["size"] is None:
        flags.append("missing_size")
    if out["unit"] is not None and len(out["unit"]) > 8:
        flags.append("unit_suspicious")
    if out["unit"] is not None and out["size"] is not None and "inch" in str(out["size"]).lower() and str(out["unit"]).lower() in ["mm", "cm"]:
        flags.append("unit_size_mismatch")
    return out, flags


def _ensure_storage_bucket(svc) -> None:
    bucket_id = settings.supabase_bucket
    try:
        buckets = svc.storage.list_buckets()
        for b in buckets:
            if getattr(b, "id", None) == bucket_id:
                return
        svc.storage.create_bucket(bucket_id, options={"public": False})
        logger.info("storage_bucket: created", extra={"bucket": bucket_id})
    except Exception as e:
        logger.error("storage_bucket: ensure failed", extra={"bucket": bucket_id, "error": str(e)})
        raise


@app.get("/")
def serve_index():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"ok": True, "message": "Frontend belum dibuat"})


@app.get("/api/health")
def health_check():
    missing: list[str] = []
    try:
        require_supabase_anon()
    except RuntimeError as e:
        missing.append(str(e))
    try:
        require_supabase_service()
    except RuntimeError as e:
        missing.append(str(e))

    try:
        svc = get_supabase_service()
        buckets = svc.storage.list_buckets()
        if not any(getattr(b, "id", None) == settings.supabase_bucket for b in buckets):
            missing.append(f"Supabase Storage bucket not found: {settings.supabase_bucket}")
    except Exception as e:
        missing.append(f"Supabase Storage check failed: {e}")

    return {"ok": len(missing) == 0, "checks": missing}


@app.post("/api/auth/sign-up", response_model=AuthSession)
def sign_up(payload: AuthRequest):
    try:
        anon = get_supabase_anon()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    email_fp = _email_fingerprint(payload.email)
    try:
        if _email_exists(payload.email):
            logger.info("sign_up: duplicate_email", extra={"email_fp": email_fp})
            raise _duplicate_email_http()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("sign_up: email_exists check failed", extra={"email_fp": email_fp, "error": str(e)})

    try:
        svc = get_supabase_service()
        created = svc.auth.admin.create_user(
            {
                "email": payload.email,
                "password": payload.password,
                "email_confirm": True,
            }
        )
    except Exception as e:
        msg = str(e)
        if "already been registered" in msg.lower() or "already registered" in msg.lower():
            logger.info("sign_up: duplicate_email (create_user)", extra={"email_fp": email_fp})
            raise _duplicate_email_http()
        raise HTTPException(status_code=400, detail=msg)

    user_id = getattr(created.user, "id", None) if created is not None else None
    if not user_id:
        raise HTTPException(status_code=400, detail="Sign up gagal: user tidak tersedia")

    try:
        login = anon.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
    except Exception as e:
        logger.warning("sign_up: auto sign-in failed", extra={"user_id": user_id, "error": str(e)})
        raise HTTPException(status_code=400, detail="Akun dibuat, tapi auto-login gagal. Silakan login.")

    if login.session is None:
        raise HTTPException(status_code=400, detail="Akun dibuat, tapi session tidak tersedia")

    s = login.session
    logger.info("sign_up: authenticated", extra={"user_id": str(user_id)})
    return AuthSession(
        access_token=s.access_token,
        refresh_token=s.refresh_token,
        expires_in=s.expires_in,
        token_type=s.token_type,
        user_id=str(user_id),
    )


@app.get("/api/auth/email-availability", response_model=EmailAvailabilityResponse)
def email_availability(email: str):
    email_fp = _email_fingerprint(email)
    norm = (email or "").strip()
    if not norm or "@" not in norm:
        raise HTTPException(status_code=400, detail="Email tidak valid")
    try:
        exists = _email_exists(norm)
    except Exception as e:
        logger.warning("email_availability: failed", extra={"email_fp": email_fp, "error": str(e)})
        raise HTTPException(status_code=500, detail="Gagal memeriksa email")
    return EmailAvailabilityResponse(available=not exists)


@app.post("/api/auth/password-recovery")
def password_recovery(payload: EmailRequest):
    email = (payload.email or "").strip()
    email_fp = _email_fingerprint(email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email tidak valid")
    try:
        anon = get_supabase_anon()
        anon.auth.reset_password_for_email(email)
        logger.info("password_recovery: requested", extra={"email_fp": email_fp})
    except Exception as e:
        logger.warning("password_recovery: failed", extra={"email_fp": email_fp, "error": str(e)})
    return {"ok": True}


@app.post("/api/auth/sign-in", response_model=AuthSession)
def sign_in(payload: AuthRequest):
    try:
        anon = get_supabase_anon()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        res = anon.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res.session is None or res.user is None:
        raise HTTPException(status_code=401, detail="Login gagal")
    s = res.session
    return AuthSession(
        access_token=s.access_token,
        refresh_token=s.refresh_token,
        expires_in=s.expires_in,
        token_type=s.token_type,
        user_id=res.user.id,
    )


@app.get("/api/me", response_model=MeResponse)
def me(user_id: str = Depends(_require_auth)):
    return MeResponse(user_id=user_id)


@app.get("/api/projects", response_model=list[ProjectWithSummary])
def list_projects(user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()

    p = svc.table("projects").select("*").eq("owner_id", user_id).order("updated_at", desc=True).execute()
    if p is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil proyek")
    projects: list[dict[str, Any]] = p.data or []

    docs_by_project: dict[str, int] = {}
    mats_by_project: dict[str, int] = {}

    docs_res = svc.table("documents").select("project_id").eq("owner_id", user_id).execute()
    if docs_res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    docs = docs_res.data or []
    for d in docs:
        pid = d.get("project_id")
        if pid:
            docs_by_project[pid] = docs_by_project.get(pid, 0) + 1

    mats_res = svc.table("materials").select("project_id", "quantity", "unit").eq("owner_id", user_id).execute()
    if mats_res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil material")
    mats = mats_res.data or []
    for m in mats:
        pid = m.get("project_id")
        if pid:
            mats_by_project[pid] = mats_by_project.get(pid, 0) + 1

    pipe_len_by_project: dict[str, float] = {}
    for m in mats:
        pid = m.get("project_id")
        if not pid:
            continue
        unit = (m.get("unit") or "").lower()
        qty = m.get("quantity")
        if qty is None:
            continue
        if unit in ["m", "meter", "meters"]:
            pipe_len_by_project[pid] = pipe_len_by_project.get(pid, 0.0) + float(qty)

    out: list[ProjectWithSummary] = []
    for pr in projects:
        pid = pr["id"]
        out.append(
            ProjectWithSummary(
                **pr,
                total_documents=docs_by_project.get(pid, 0),
                total_material_rows=mats_by_project.get(pid, 0),
                total_pipe_length_m=pipe_len_by_project.get(pid, 0.0),
            )
        )
    return out


@app.post("/api/projects", response_model=Project)
def create_project(payload: ProjectCreate, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    now = datetime.utcnow().isoformat()
    row = {
        "id": str(uuid4()),
        "owner_id": user_id,
        "name": payload.name,
        "location": payload.location,
        "year": payload.year,
        "status": payload.status,
        "description": payload.description,
        "created_at": now,
        "updated_at": now,
    }
    res = svc.table("projects").insert(row).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal membuat proyek")
    if not res.data:
        raise HTTPException(status_code=400, detail="Gagal membuat proyek")
    return res.data[0]


@app.get("/api/projects/{project_id}", response_model=Project)
def get_project(project_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    res = svc.table("projects").select("*").eq("id", project_id).eq("owner_id", user_id).limit(1).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil proyek")
    if not res.data:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")
    return res.data[0]


@app.patch("/api/projects/{project_id}", response_model=Project)
def update_project(project_id: str, payload: ProjectUpdate, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    patch["updated_at"] = datetime.utcnow().isoformat()
    res = (
        svc.table("projects")
        .update(patch)
        .eq("id", project_id)
        .eq("owner_id", user_id)
        .execute()
    )
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal update proyek")
    if not res.data:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")
    return res.data[0]


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    res = svc.table("projects").delete().eq("id", project_id).eq("owner_id", user_id).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal menghapus proyek")
    return {"deleted": len(res.data or [])}


@app.get("/api/projects/{project_id}/documents", response_model=list[Document])
def list_documents(project_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    docs_res = (
        svc.table("documents")
        .select("*")
        .eq("project_id", project_id)
        .eq("owner_id", user_id)
        .order("uploaded_at", desc=True)
        .execute()
    )
    if docs_res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    docs = docs_res.data or []

    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    out: list[Document] = []
    for d in docs:
        download_url = None
        try:
            signed = storage.create_signed_url(d["storage_path"], settings.signed_url_expires_seconds)
            download_url = signed.get("signedURL")
        except Exception:
            download_url = None
        d["download_url"] = download_url
        out.append(Document(**d))
    return out


@app.post("/api/projects/{project_id}/documents", response_model=Document)
async def upload_document(project_id: str, file: UploadFile = File(...), user_id: str = Depends(_require_auth)):
    filename_in = file.filename or ""

    svc = get_supabase_service()
    pr = svc.table("projects").select("id").eq("id", project_id).eq("owner_id", user_id).limit(1).execute()
    if pr is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil proyek")
    if not pr.data:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")

    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Gagal membaca file")

    content_type_in = (file.content_type or "").lower() or None

    try:
        kind = detect_upload_kind(content, filename=filename_in, content_type=content_type_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    doc_id = str(uuid4())
    original_filename = os.path.basename(filename_in) if filename_in else None
    now = datetime.utcnow().isoformat()

    mime_type = "application/pdf"
    file_kind = "pdf"
    image_w: int | None = None
    image_h: int | None = None
    file_size_bytes: int | None = None

    if kind == "image":
        try:
            out_bytes, w, h, out_mime, out_ext = validate_and_convert_image_upload(
                content,
                filename=original_filename or "upload.png",
                content_type=content_type_in,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        content = out_bytes
        mime_type = out_mime
        file_kind = "image"
        image_w = w
        image_h = h
        file_size_bytes = len(content)
        ext_out = out_ext if out_ext and out_ext.startswith(".") else ".png"
        filename = f"{doc_id}{ext_out}"
        storage_path = f"{user_id}/{project_id}/images/{filename}"
    else:
        pdf_name = os.path.basename(filename_in) if filename_in else f"{doc_id}.pdf"
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name = f"{pdf_name}.pdf"
        filename = pdf_name
        storage_path = f"{user_id}/{project_id}/{doc_id}/{filename}"
        file_size_bytes = len(content)

    row = {
        "id": doc_id,
        "project_id": project_id,
        "owner_id": user_id,
        "storage_path": storage_path,
        "filename": filename,
        "document_type": "Lainnya",
        "document_number": None,
        "document_date": None,
        "status": "uploaded",
        "uploaded_at": now,
        "file_kind": file_kind,
        "mime_type": mime_type,
        "file_size_bytes": file_size_bytes,
        "image_width": image_w,
        "image_height": image_h,
        "original_filename": original_filename,
    }

    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        storage.upload(storage_path, content, cast(Any, _storage_file_options(mime_type)))
    except Exception as e:
        msg = str(e)
        if "bucket not found" in msg.lower():
            raise HTTPException(status_code=500, detail=f"Storage bucket tidak ditemukan: {settings.supabase_bucket}")
        raise HTTPException(status_code=400, detail=f"Upload ke storage gagal: {e}")

    ins = svc.table("documents").insert(row).execute()
    if ins is None:
        raise HTTPException(status_code=500, detail="Simpan metadata dokumen gagal")
    if not ins.data:
        raise HTTPException(status_code=400, detail="Simpan metadata dokumen gagal")

    try:
        signed = storage.create_signed_url(storage_path, settings.signed_url_expires_seconds)
        row["download_url"] = signed.get("signedURL")
    except Exception:
        row["download_url"] = None

    return Document(**row)


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).limit(1).execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    storage_path = doc.data[0]["storage_path"]

    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        storage.remove([storage_path])
    except Exception:
        pass

    svc.table("documents").delete().eq("id", document_id).eq("owner_id", user_id).execute()
    return {"deleted": True}


@app.get("/api/projects/{project_id}/materials", response_model=list[Material])
def list_materials(
    project_id: str,
    q: str | None = None,
    size: str | None = None,
    document_id: str | None = None,
    user_id: str = Depends(_require_auth),
):
    svc = get_supabase_service()
    query = svc.table("materials").select("*").eq("project_id", project_id).eq("owner_id", user_id)
    if document_id:
        query = query.eq("document_id", document_id)
    if size:
        query = query.ilike("size", f"%{size}%")
    if q:
        query = query.ilike("description", f"%{q}%")
    res = query.order("created_at", desc=True).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil material")
    return [Material(**m) for m in (res.data or [])]


@app.get("/api/projects/{project_id}/materials/page", response_model=MaterialListResponse)
def list_materials_page(
    project_id: str,
    q: str | None = None,
    size: str | None = None,
    unit: str | None = None,
    document_id: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    limit: int = 200,
    offset: int = 0,
    user_id: str = Depends(_require_auth),
):
    svc = get_supabase_service()

    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))

    sort_map = {
        "created_at": "created_at",
        "name": "description",
        "description": "description",
        "size": "size",
        "quantity": "quantity",
        "unit": "unit",
    }
    col = sort_map.get((sort_by or "created_at").lower(), "created_at")
    desc = (sort_dir or "desc").lower() != "asc"

    query = svc.table("materials").select("*").eq("project_id", project_id).eq("owner_id", user_id)
    if document_id:
        query = query.eq("document_id", document_id)
    if size:
        query = query.ilike("size", f"%{size}%")
    if unit:
        query = query.ilike("unit", f"%{unit}%")
    if q:
        pat = f"%{q}%"
        if hasattr(query, "or_"):
            query = query.or_(f"description.ilike.{pat},spec.ilike.{pat}")
        else:
            query = query.ilike("description", pat)

    query = query.order(col, desc=desc)
    if hasattr(query, "range"):
        res = query.range(offset, offset + limit).execute()
        if res is None:
            raise HTTPException(status_code=500, detail="Gagal mengambil material")
        data = res.data or []
    else:
        res = query.execute()
        if res is None:
            raise HTTPException(status_code=500, detail="Gagal mengambil material")
        data = (res.data or [])[offset : offset + limit + 1]

    has_more = len(data) > limit
    items = data[:limit]
    next_offset = offset + limit if has_more else None
    return {
        "items": [Material(**m) for m in items],
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
    }


@app.post("/api/projects/{project_id}/materials", response_model=Material)
def create_material(project_id: str, payload: MaterialCreate, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    row = {
        "id": str(uuid4()),
        "owner_id": user_id,
        "project_id": project_id,
        "document_id": payload.document_id,
        "description": payload.description,
        "size": payload.size,
        "quantity": payload.quantity,
        "unit": payload.unit,
        "heat_no": payload.heat_no,
        "tag_no": payload.tag_no,
        "spec": payload.spec,
        "created_at": datetime.utcnow().isoformat(),
    }
    res = svc.table("materials").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Gagal menambah material")
    return res.data[0]


@app.patch("/api/materials/{material_id}", response_model=Material)
def update_material(material_id: str, payload: MaterialUpdate, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    existing = svc.table("materials").select("*").eq("id", material_id).eq("owner_id", user_id).limit(1).execute()
    if existing is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil material")
    if not existing.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")

    before = dict(existing.data[0])
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    res = svc.table("materials").update(patch).eq("id", material_id).eq("owner_id", user_id).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal update material")
    if not res.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")

    try:
        after = dict(res.data[0])
        _insert_item_revision(
            svc,
            owner_id=user_id,
            project_id=str(after.get("project_id") or before.get("project_id") or ""),
            document_id=str(after.get("document_id") or before.get("document_id") or "") or None,
            material_id=material_id,
            change_source="manual_edit",
            before={k: before.get(k) for k in ["description", "spec", "size", "quantity", "unit", "verification_status", "needs_review"]},
            after={k: after.get(k) for k in ["description", "spec", "size", "quantity", "unit", "verification_status", "needs_review"]},
            changed_by=user_id,
            ocr_run_id=str(after.get("ocr_run_id") or "") or None,
            ocr_extraction_id=str(after.get("ocr_extraction_id") or "") or None,
        )
    except Exception:
        pass
    return res.data[0]


@app.get("/api/materials/{material_id}/history")
def material_history(material_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    m = svc.table("materials").select("project_id", "document_id").eq("id", material_id).eq("owner_id", user_id).limit(1).execute()
    if m is None or not m.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    res = (
        svc.table("item_revisions")
        .select("*")
        .eq("material_id", material_id)
        .eq("owner_id", user_id)
        .order("changed_at", desc=True)
        .limit(50)
        .execute()
    )
    return res.data or []


@app.get("/api/materials/{material_id}/ocr-context")
def material_ocr_context(material_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    m = svc.table("materials").select("*").eq("id", material_id).eq("owner_id", user_id).limit(1).execute()
    if m is None or not m.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    mat = m.data[0]

    run = None
    ext = None
    run_id = str(mat.get("ocr_run_id") or "")
    ext_id = str(mat.get("ocr_extraction_id") or "")

    if run_id:
        r = svc.table("ocr_runs").select("*").eq("id", run_id).eq("owner_id", user_id).limit(1).execute()
        run = (r.data[0] if (r is not None and r.data) else None)
    if ext_id:
        e = svc.table("ocr_item_extractions").select("*").eq("id", ext_id).eq("owner_id", user_id).limit(1).execute()
        ext = (e.data[0] if (e is not None and e.data) else None)
    return {"material": mat, "ocr_run": run, "ocr_extraction": ext}


@app.post("/api/materials/{material_id}/review")
async def review_material(material_id: str, request: Request, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    body = await request.json()
    decision = str((body or {}).get("decision") or "").strip().lower()
    notes = (body or {}).get("notes")
    patch_in = (body or {}).get("patch") or {}

    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision harus approved atau rejected")

    existing = svc.table("materials").select("*").eq("id", material_id).eq("owner_id", user_id).limit(1).execute()
    if existing is None or not existing.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    before = dict(existing.data[0])

    now = _utc_now_iso()
    patch: dict[str, Any] = {}
    for k in ["description", "spec", "size", "quantity", "unit"]:
        if k in patch_in:
            patch[k] = patch_in.get(k)

    if decision == "approved":
        patch["verification_status"] = "approved"
        patch["needs_review"] = False
        patch["verified_by"] = user_id
        patch["verified_at"] = now
    else:
        patch["verification_status"] = "rejected"
        patch["needs_review"] = False
        patch["verified_by"] = user_id
        patch["verified_at"] = now

    res = svc.table("materials").update(patch).eq("id", material_id).eq("owner_id", user_id).execute()
    if res is None or not res.data:
        raise HTTPException(status_code=500, detail="Gagal menyimpan review")
    after = dict(res.data[0])

    svc.table("review_decisions").insert(
        {
            "id": str(uuid4()),
            "owner_id": user_id,
            "project_id": after.get("project_id"),
            "document_id": after.get("document_id"),
            "material_id": material_id,
            "ocr_extraction_id": after.get("ocr_extraction_id"),
            "decision": decision,
            "notes": notes,
            "decided_by": user_id,
            "decided_at": now,
        }
    ).execute()

    try:
        _insert_item_revision(
            svc,
            owner_id=user_id,
            project_id=str(after.get("project_id") or ""),
            document_id=str(after.get("document_id") or "") or None,
            material_id=material_id,
            change_source="ocr_verify" if decision == "approved" else "ocr_reject",
            before={k: before.get(k) for k in ["description", "spec", "size", "quantity", "unit", "verification_status", "needs_review"]},
            after={k: after.get(k) for k in ["description", "spec", "size", "quantity", "unit", "verification_status", "needs_review"]},
            changed_by=user_id,
            ocr_run_id=str(after.get("ocr_run_id") or "") or None,
            ocr_extraction_id=str(after.get("ocr_extraction_id") or "") or None,
        )
    except Exception:
        pass

    return after


@app.delete("/api/materials/{material_id}")
def delete_material(material_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    res = svc.table("materials").delete().eq("id", material_id).eq("owner_id", user_id).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal menghapus material")
    return {"deleted": len(res.data or [])}


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).limit(1).execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return doc.data[0]


@app.get("/api/documents/{document_id}/extraction-runs")
def list_extraction_runs(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    runs_res = (
        svc.table("extraction_runs")
        .select("*")
        .eq("document_id", document_id)
        .eq("owner_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    if runs_res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil extraction runs")
    return runs_res.data or []


@app.post("/api/documents/{document_id}/extract", response_model=ExtractionResponse)
async def extract_document(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).limit(1).execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    d = doc.data[0]

    inferred_kind = (str(d.get("file_kind") or "").strip().lower() or None)
    if inferred_kind is None:
        sp = str(d.get("storage_path") or "")
        fn = str(d.get("filename") or "")
        if "/images/" in sp.replace("\\", "/") or fn.lower().endswith((".png", ".jpg", ".jpeg")):
            inferred_kind = "image"
        else:
            inferred_kind = "pdf"

    if inferred_kind != "pdf":
        raise HTTPException(
            status_code=400,
            detail=(
                "Dokumen ini berupa gambar. Ekstraksi hanya tersedia untuk PDF. "
                "Langkah yang bisa dilakukan: (1) jalankan OCR MTO untuk gambar via /api/documents/{id}/mto, "
                "atau (2) konversi gambar ke PDF via /api/documents/{id}/convert-to-pdf."
            ),
        )
    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        signed = storage.create_signed_url(d["storage_path"], 300)
        url = signed.get("signedURL")
        if not url:
            raise Exception("signed url kosong")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Tidak bisa akses file di storage: {e}")

    import httpx

    try:
        r = httpx.get(url, timeout=60.0)
        r.raise_for_status()
        file_bytes = r.content
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal download file untuk ekstraksi: {e}")

    try:
        kind = detect_upload_kind(file_bytes, filename=str(d.get("filename") or ""), content_type=str(d.get("mime_type") or "") or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if kind != "pdf":
        raise HTTPException(
            status_code=400,
            detail=(
                "Konten file yang tersimpan bukan PDF. Ekstraksi hanya tersedia untuk PDF. "
                "Langkah yang bisa dilakukan: (1) jalankan OCR MTO untuk gambar via /api/documents/{id}/mto, "
                "atau (2) konversi gambar ke PDF via /api/documents/{id}/convert-to-pdf."
            ),
        )

    svc.table("documents").update({"status": "extracting"}).eq("id", document_id).eq("owner_id", user_id).execute()

    method = "pdf_text"
    notes: str | None = None
    text = ""
    inserted = 0
    extracted_json: dict[str, Any] = {}

    try:
        text = extract_pdf_text(file_bytes)
        if len(text.strip()) < 200:
            try:
                ocr_text, ocr_note = ocr_pdf_text(file_bytes)
            except Exception as e:
                logger.exception("ocr_pdf_text_failed: doc=%s", document_id)
                ocr_text, ocr_note = "", f"OCR error: {e}"

            if ocr_text.strip():
                text = ocr_text
                method = "pdf_text_then_ocr"
                notes = ocr_note
            else:
                method = "pdf_text_then_ocr"
                notes = ocr_note or "OCR tidak menghasilkan teks"

        extracted_json = build_extracted_json(text, method=method, notes=notes)
        info = parse_doc_info(text)

        mats: list[dict[str, Any]] = []
        parse_warnings: list[str] = []
        parser_used = "pdf_words_table"
        try:
            mats, parse_warnings = parse_materials_from_pdf_bytes(file_bytes, max_rows=5000)
        except Exception as e:
            logger.exception("parse_materials_from_pdf_bytes_failed: doc=%s", document_id)
            parse_warnings = [f"parse_materials_from_pdf_bytes error: {e}"]
            mats = []

        if not mats:
            parser_used = "text_lines"
            if len(text.strip()) >= 10:
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
        ).eq("id", document_id).eq("owner_id", user_id).execute()

        if mats:
            svc.table("materials").delete().eq("document_id", document_id).eq("owner_id", user_id).execute()
            to_insert: list[dict[str, Any]] = []
            for m in mats:
                to_insert.append(
                    {
                        "id": str(uuid4()),
                        "owner_id": user_id,
                        "project_id": d["project_id"],
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
            if ins is None:
                raise HTTPException(status_code=500, detail="Gagal menyimpan material")
            inserted = len(ins.data or [])

        run_id = str(uuid4())
        run_row = {
            "id": run_id,
            "owner_id": user_id,
            "document_id": document_id,
            "method": method,
            "status": "success" if success else "failed",
            "extracted_json": extracted_json,
            "notes": notes,
            "created_at": datetime.utcnow().isoformat(),
        }
        svc.table("extraction_runs").insert(run_row).execute()

        run_res = svc.table("extraction_runs").select("*").eq("id", run_id).eq("owner_id", user_id).limit(1).execute()
        if run_res is None:
            raise HTTPException(status_code=500, detail="Gagal mengambil hasil ekstraksi")
        run = (run_res.data or [None])[0]
        return {"run": run, "inserted_materials": inserted}
    except HTTPException as e:
        logger.exception("extract_failed: doc=%s", document_id)
        try:
            svc.table("documents").update({"status": "failed"}).eq("id", document_id).eq("owner_id", user_id).execute()
            svc.table("extraction_runs").insert(
                {
                    "id": str(uuid4()),
                    "owner_id": user_id,
                    "document_id": document_id,
                    "method": method,
                    "status": "failed",
                    "extracted_json": extracted_json or None,
                    "notes": str(e.detail),
                    "created_at": datetime.utcnow().isoformat(),
                }
            ).execute()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("extract_failed: doc=%s", document_id)
        try:
            svc.table("documents").update({"status": "failed"}).eq("id", document_id).eq("owner_id", user_id).execute()
            svc.table("extraction_runs").insert(
                {
                    "id": str(uuid4()),
                    "owner_id": user_id,
                    "document_id": document_id,
                    "method": method,
                    "status": "failed",
                    "extracted_json": extracted_json or None,
                    "notes": str(e),
                    "created_at": datetime.utcnow().isoformat(),
                }
            ).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Ekstraksi gagal: {e}")


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox harus format: x0,y0,x1,y1")
    try:
        x0, y0, x1, y1 = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except Exception:
        raise HTTPException(status_code=400, detail="bbox harus angka: x0,y0,x1,y1")
    return (x0, y0, x1, y1)


async def _download_document_bytes(svc, storage_path: str) -> bytes:
    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        signed = storage.create_signed_url(storage_path, 300)
        url = signed.get("signedURL")
        if not url:
            raise Exception("signed url kosong")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Tidak bisa akses file di storage: {e}")

    import httpx

    try:
        r = httpx.get(url, timeout=60.0)
        r.raise_for_status()
        return r.content
    except httpx.HTTPStatusError as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 404:
            raise HTTPException(status_code=404, detail="File tidak ditemukan di storage (404)")
        raise HTTPException(status_code=400, detail=f"Gagal download file: HTTP {status}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal download file: {e}")


def _upload_output_bytes(
    svc,
    *,
    user_id: str,
    project_id: str,
    document_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any]:
    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    storage_path = f"{user_id}/{project_id}/outputs/{document_id}/{filename}"
    try:
        storage.upload(storage_path, content, cast(Any, _storage_file_options(content_type)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload output gagal: {e}")

    download_url = None
    try:
        signed = storage.create_signed_url(storage_path, settings.signed_url_expires_seconds)
        download_url = signed.get("signedURL")
    except Exception:
        download_url = None

    return {"storage_path": storage_path, "download_url": download_url, "content_type": content_type, "bytes": len(content)}


def _require_doc_owner(svc, document_id: str, user_id: str) -> dict[str, Any]:
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).limit(1).execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return doc.data[0]


def _parse_bool_param(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return None


async def _get_params_query_or_form(request: Request) -> dict[str, str]:
    qp: dict[str, str] = {k: v for k, v in request.query_params.items()}
    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
        try:
            form = await request.form()
            for k, v in form.items():
                if k not in qp:
                    if hasattr(v, "filename"):
                        continue
                    qp[k] = str(v)
        except Exception:
            pass
    return qp


@app.post("/api/documents/{document_id}/mto")
async def extract_mto_from_document(
    document_id: str,
    request: Request,
    user_id: str = Depends(_require_auth),
):
    params = await _get_params_query_or_form(request)
    try:
        page_index = int(params.get("page_index") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="page_index harus berupa integer")
    bbox = cast(str | None, params.get("bbox"))
    split_columns = _parse_bool_param(params.get("split_columns"))
    svc = get_supabase_service()
    d = _require_doc_owner(svc, document_id, user_id)
    file_kind = (str(d.get("file_kind") or "").strip().lower() or "pdf")
    storage_path = str(d.get("storage_path") or "")
    if not storage_path:
        raise HTTPException(status_code=400, detail="storage_path kosong")

    raw = await _download_document_bytes(svc, storage_path)

    logger.info("mto_extract: doc=%s kind=%s page_index=%s", document_id, file_kind, page_index)

    try:
        kind = detect_upload_kind(raw, filename=str(d.get("filename") or ""), content_type=str(d.get("mime_type") or "") or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if file_kind == "image" or kind == "image":
        try:
            rows = extract_mto_from_image_bytes_advanced(raw, bbox=_parse_bbox(bbox), split_columns=split_columns)
        except Exception as e:
            msg = str(e)
            if "Tesseract OCR tidak terdeteksi" in msg or "pytesseract tidak tersedia" in msg:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "OCR belum tersedia di server. Install Tesseract OCR di Windows dan pastikan tesseract.exe ada di PATH, "
                        "atau set env TESSERACT_CMD. Setelah itu ulangi OCR MTO. Jika perlu, gunakan opsi konversi gambar ke PDF."
                    ),
                )
            logger.exception("mto_extract_failed: doc=%s", document_id)
            raise HTTPException(status_code=400, detail=f"OCR MTO gagal: {e}")

        proj_id = str(d.get("project_id") or "")
        txt_lines = ["item\tmaterial\tdescription\tnps\tqty_value\tqty_unit\tsource"]
        for r in rows:
            txt_lines.append(
                "\t".join(
                    [
                        str(r.get("item") or ""),
                        str(r.get("material") or ""),
                        str(r.get("description") or ""),
                        str(r.get("nps") or ""),
                        str(r.get("qty_value") or ""),
                        str(r.get("qty_unit") or ""),
                        str(r.get("source") or ""),
                    ]
                )
            )
        txt_bytes = ("\n".join(txt_lines) + "\n").encode("utf-8")

        csv_buf = io.StringIO()
        w = csv.DictWriter(
            csv_buf,
            fieldnames=["item", "material", "description", "nps", "qty_value", "qty_unit", "source"],
            extrasaction="ignore",
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
        csv_bytes = csv_buf.getvalue().encode("utf-8")

        out_txt = _upload_output_bytes(
            svc,
            user_id=user_id,
            project_id=proj_id,
            document_id=document_id,
            filename=f"mto_page{int(page_index)}.txt",
            content=txt_bytes,
            content_type="text/plain; charset=utf-8",
        )
        out_csv = _upload_output_bytes(
            svc,
            user_id=user_id,
            project_id=proj_id,
            document_id=document_id,
            filename=f"mto_page{int(page_index)}.csv",
            content=csv_bytes,
            content_type="text/csv; charset=utf-8",
        )

        return {"items": rows, "outputs": {"txt": out_txt, "csv": out_csv}}

    try:
        rows = extract_mto_from_pdf_bytes_advanced(raw, int(page_index), bbox=_parse_bbox(bbox), split_columns=split_columns)
    except Exception as e:
        logger.exception("mto_extract_failed: doc=%s", document_id)
        raise HTTPException(status_code=400, detail=f"OCR MTO gagal: {e}")
    
    proj_id = str(d.get("project_id") or "")
    txt_lines = ["item\tmaterial\tdescription\tnps\tqty_value\tqty_unit\tsource"]
    for r in rows:
        txt_lines.append(
            "\t".join(
                [
                    str(r.get("item") or ""),
                    str(r.get("material") or ""),
                    str(r.get("description") or ""),
                    str(r.get("nps") or ""),
                    str(r.get("qty_value") or ""),
                    str(r.get("qty_unit") or ""),
                    str(r.get("source") or ""),
                ]
            )
        )
    txt_bytes = ("\n".join(txt_lines) + "\n").encode("utf-8")

    csv_buf = io.StringIO()
    w = csv.DictWriter(
        csv_buf,
        fieldnames=["item", "material", "description", "nps", "qty_value", "qty_unit", "source"],
        extrasaction="ignore",
    )
    w.writeheader()
    for r in rows:
        w.writerow(r)
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    out_txt = _upload_output_bytes(
        svc,
        user_id=user_id,
        project_id=proj_id,
        document_id=document_id,
        filename=f"mto_page{int(page_index)}.txt",
        content=txt_bytes,
        content_type="text/plain; charset=utf-8",
    )
    out_csv = _upload_output_bytes(
        svc,
        user_id=user_id,
        project_id=proj_id,
        document_id=document_id,
        filename=f"mto_page{int(page_index)}.csv",
        content=csv_bytes,
        content_type="text/csv; charset=utf-8",
    )

    return {"items": rows, "outputs": {"txt": out_txt, "csv": out_csv}}


@app.post("/api/documents/{document_id}/mto/import")
async def import_mto_ocr(document_id: str, request: Request, user_id: str = Depends(_require_auth)):
    params = await _get_params_query_or_form(request)
    try:
        page_index = int(params.get("page_index") or 0)
    except Exception:
        raise HTTPException(status_code=400, detail="page_index harus berupa integer")
    bbox = cast(str | None, params.get("bbox"))
    split_columns = _parse_bool_param(params.get("split_columns"))

    svc = get_supabase_service()
    d = _require_doc_owner(svc, document_id, user_id)
    storage_path = str(d.get("storage_path") or "")
    if not storage_path:
        raise HTTPException(status_code=400, detail="storage_path kosong")
    raw = await _download_document_bytes(svc, storage_path)

    file_kind = (str(d.get("file_kind") or "").strip().lower() or "pdf")
    try:
        kind = detect_upload_kind(raw, filename=str(d.get("filename") or ""), content_type=str(d.get("mime_type") or "") or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        if file_kind == "image" or kind == "image":
            rows = extract_mto_from_image_bytes_advanced(raw, bbox=_parse_bbox(bbox), split_columns=split_columns)
        else:
            rows = extract_mto_from_pdf_bytes_advanced(raw, int(page_index), bbox=_parse_bbox(bbox), split_columns=split_columns)
    except Exception as e:
        msg = str(e)
        if "Tesseract OCR tidak terdeteksi" in msg or "pytesseract tidak tersedia" in msg:
            raise HTTPException(
                status_code=400,
                detail=(
                    "OCR belum tersedia di server. Install Tesseract OCR di Windows dan pastikan tesseract.exe ada di PATH, "
                    "atau set env TESSERACT_CMD. Setelah itu ulangi OCR MTO."
                ),
            )
        logger.exception("mto_import_failed: doc=%s", document_id)
        raise HTTPException(status_code=400, detail=f"OCR MTO gagal: {e}")

    run_id = str(uuid4())
    now = _utc_now_iso()
    engine_version = _tesseract_engine_version()
    run_row = {
        "id": run_id,
        "owner_id": user_id,
        "project_id": d.get("project_id"),
        "document_id": document_id,
        "engine_name": "tesseract",
        "engine_version": engine_version,
        "processed_at": now,
        "input_file_kind": file_kind,
        "input_filename": d.get("filename"),
        "input_storage_path": d.get("storage_path"),
        "created_at": now,
    }
    svc.table("ocr_runs").insert(run_row).execute()
    svc.table("documents").update({"last_ocr_run_id": run_id, "last_ocr_processed_at": now}).eq("id", document_id).eq("owner_id", user_id).execute()

    try:
        svc.table("materials").delete().eq("document_id", document_id).eq("owner_id", user_id).eq("data_source", "ocr").execute()
    except Exception:
        pass

    extractions: list[dict[str, Any]] = []
    mats_to_insert: list[dict[str, Any]] = []
    flagged = 0
    for r in rows:
        norm, flags = _mto_row_to_material_fields(r)
        needs_review = len(flags) > 0
        if needs_review:
            flagged += 1
        extraction_id = str(uuid4())
        extractions.append(
            {
                "id": extraction_id,
                "owner_id": user_id,
                "project_id": d.get("project_id"),
                "document_id": document_id,
                "ocr_run_id": run_id,
                "page_index": int(page_index),
                "line_no": int(r.get("item") or 0) if str(r.get("item") or "").isdigit() else None,
                "raw_payload": r,
                "normalized_fields": norm,
                "confidence": None,
                "flags": {"flags": flags, "needs_review": needs_review},
                "created_at": now,
            }
        )

        mats_to_insert.append(
            {
                "id": str(uuid4()),
                "owner_id": user_id,
                "project_id": d.get("project_id"),
                "document_id": document_id,
                "description": norm.get("description") or "",
                "spec": norm.get("spec"),
                "size": norm.get("size"),
                "quantity": norm.get("quantity"),
                "unit": norm.get("unit"),
                "heat_no": None,
                "tag_no": None,
                "created_at": now,
                "data_source": "ocr",
                "verification_status": "needs_review" if needs_review else "draft",
                "needs_review": needs_review,
                "ocr_run_id": run_id,
                "ocr_extraction_id": extraction_id,
            }
        )

    if extractions:
        svc.table("ocr_item_extractions").insert(extractions).execute()
    inserted = 0
    if mats_to_insert:
        ins = svc.table("materials").insert(mats_to_insert).execute()
        inserted = len(ins.data or [])

    return {
        "ocr_run": run_row,
        "items": rows,
        "inserted_materials": inserted,
        "flagged": flagged,
    }


@app.get("/api/documents/{document_id}/mto/ocr-latest")
def get_latest_mto_ocr(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    run_res = (
        svc.table("ocr_runs")
        .select("*")
        .eq("document_id", document_id)
        .eq("owner_id", user_id)
        .order("processed_at", desc=True)
        .limit(1)
        .execute()
    )
    runs = run_res.data or []
    if not runs:
        return {"ocr_run": None, "items": [], "materials": []}
    run = runs[0]
    run_id = run["id"]
    exts = (
        svc.table("ocr_item_extractions")
        .select("*")
        .eq("ocr_run_id", run_id)
        .eq("owner_id", user_id)
        .order("line_no", desc=False)
        .execute()
    ).data or []
    mats = (
        svc.table("materials")
        .select("*")
        .eq("ocr_run_id", run_id)
        .eq("owner_id", user_id)
        .order("created_at", desc=False)
        .execute()
    ).data or []
    items = [e.get("raw_payload") for e in exts if e.get("raw_payload")]
    return {"ocr_run": run, "items": items, "materials": mats, "extractions": exts}


@app.post("/api/documents/{document_id}/mto/csv")
async def extract_mto_from_document_csv(document_id: str, request: Request, user_id: str = Depends(_require_auth)):
    payload = await extract_mto_from_document(document_id, request, user_id=user_id)
    rows = (payload or {}).get("items") or []

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["item", "material", "description", "nps", "qty_value", "qty_unit", "source"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    out = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": "attachment; filename=materials_take_off.csv"}
    return StreamingResponse(iter([out]), media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/documents/{document_id}/convert-to-pdf", response_model=Document)
async def convert_document_image_to_pdf(document_id: str, user_id: str = Depends(_require_auth)):
    svc = get_supabase_service()
    d = _require_doc_owner(svc, document_id, user_id)
    file_kind = (str(d.get("file_kind") or "").strip().lower() or "pdf")
    storage_path = str(d.get("storage_path") or "")
    if not storage_path:
        raise HTTPException(status_code=400, detail="storage_path kosong")

    if file_kind != "image":
        raise HTTPException(status_code=400, detail="Dokumen ini bukan gambar")

    raw = await _download_document_bytes(svc, storage_path)
    logger.info("convert_to_pdf: doc=%s", document_id)
    try:
        pdf_bytes = convert_image_bytes_to_pdf(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Konversi gambar ke PDF gagal: {e}")

    new_id = str(uuid4())
    project_id = str(d.get("project_id"))
    filename = f"{new_id}.pdf"
    new_storage_path = f"{user_id}/{project_id}/{new_id}/{filename}"
    now = datetime.utcnow().isoformat()
    row = {
        "id": new_id,
        "project_id": project_id,
        "owner_id": user_id,
        "storage_path": new_storage_path,
        "filename": filename,
        "document_type": "Lainnya",
        "document_number": None,
        "document_date": None,
        "status": "uploaded",
        "uploaded_at": now,
        "file_kind": "pdf",
        "mime_type": "application/pdf",
        "file_size_bytes": len(pdf_bytes),
        "image_width": None,
        "image_height": None,
        "original_filename": d.get("original_filename") or d.get("filename"),
    }

    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        storage.upload(new_storage_path, pdf_bytes, cast(Any, _storage_file_options("application/pdf")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload PDF hasil konversi gagal: {e}")

    ins = svc.table("documents").insert(row).execute()
    if ins is None or not ins.data:
        raise HTTPException(status_code=500, detail="Simpan metadata dokumen gagal")

    try:
        signed = storage.create_signed_url(new_storage_path, settings.signed_url_expires_seconds)
        row["download_url"] = signed.get("signedURL")
    except Exception:
        row["download_url"] = None

    return Document(**row)


@app.post("/api/mto")
async def extract_mto(
    pdf: UploadFile = File(...),
    page_index: int = Form(5),
    bbox: str | None = Form(None),
    split_columns: bool | None = Form(None),
):
    try:
        pdf_bytes = await pdf.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Gagal membaca file")

    try:
        rows = extract_mto_from_pdf_bytes_advanced(
            pdf_bytes,
            int(page_index),
            bbox=_parse_bbox(bbox),
            split_columns=split_columns,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"items": rows}


@app.post("/api/mto/csv")
async def extract_mto_csv(
    pdf: UploadFile = File(...),
    page_index: int = Form(5),
    bbox: str | None = Form(None),
    split_columns: bool | None = Form(None),
):
    try:
        pdf_bytes = await pdf.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Gagal membaca file")

    try:
        rows = extract_mto_from_pdf_bytes_advanced(
            pdf_bytes,
            int(page_index),
            bbox=_parse_bbox(bbox),
            split_columns=split_columns,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["item", "material", "description", "nps", "qty_value", "qty_unit", "source"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    out = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": "attachment; filename=materials_take_off.csv"}
    return StreamingResponse(iter([out]), media_type="text/csv; charset=utf-8", headers=headers)


@app.exception_handler(HTTPException)
def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
