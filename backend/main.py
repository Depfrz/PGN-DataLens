from __future__ import annotations

import os
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
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
    ocr_pdf_text,
    parse_doc_info,
    parse_materials,
    parse_materials_from_pdf_bytes,
)


app = FastAPI(title="PGN DataLens", version="0.1.0")
security = HTTPBearer(auto_error=False)
logger = logging.getLogger("pgn_datalens")


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
    res = svc.table("projects").select("*").eq("id", project_id).eq("owner_id", user_id).maybe_single().execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil proyek")
    if not res.data:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")
    return res.data


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
    if not filename_in.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya PDF yang didukung")

    svc = get_supabase_service()
    pr = svc.table("projects").select("id").eq("id", project_id).eq("owner_id", user_id).maybe_single().execute()
    if pr is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil proyek")
    if not pr.data:
        raise HTTPException(status_code=404, detail="Proyek tidak ditemukan")

    content = await file.read()
    doc_id = str(uuid4())
    filename = os.path.basename(filename_in) if filename_in else f"{doc_id}.pdf"
    storage_path = f"{user_id}/{project_id}/{doc_id}/{filename}"
    now = datetime.utcnow().isoformat()
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
    }

    _ensure_storage_bucket(svc)
    storage = svc.storage.from_(settings.supabase_bucket)
    try:
        storage.upload(storage_path, content, cast(Any, _storage_file_options("application/pdf")))
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
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).maybe_single().execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    storage_path = doc.data["storage_path"]

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
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    res = svc.table("materials").update(patch).eq("id", material_id).eq("owner_id", user_id).execute()
    if res is None:
        raise HTTPException(status_code=500, detail="Gagal update material")
    if not res.data:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")
    return res.data[0]


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
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).maybe_single().execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return doc.data


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
    doc = svc.table("documents").select("*").eq("id", document_id).eq("owner_id", user_id).maybe_single().execute()
    if doc is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil dokumen")
    if not doc.data:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")

    d = doc.data
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

    svc.table("documents").update({"status": "extracting"}).eq("id", document_id).eq("owner_id", user_id).execute()

    text = extract_pdf_text(file_bytes)
    method = "pdf_text"
    notes = None

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

    svc.table("documents").update(
        {
            "document_type": info.document_type,
            "document_number": info.document_number,
            "status": "success" if len(text.strip()) >= 10 else "failed",
        }
    ).eq("id", document_id).eq("owner_id", user_id).execute()

    inserted = 0
    if len(text.strip()) >= 10:
        mats, parse_warnings = parse_materials_from_pdf_bytes(file_bytes, max_rows=5000)
        parser_used = "pdf_words_table" if mats else "text_lines"
        if not mats:
            mats = parse_materials(text, max_rows=5000)
            parse_warnings = []

        if parse_warnings:
            extra_notes = "\n".join(parse_warnings[:50])
            notes = (notes + "\n" + extra_notes) if notes else extra_notes

        extracted_json["materials_preview"] = mats[:20]
        extracted_json["materials_parser"] = parser_used
        if parse_warnings:
            extracted_json["warnings"] = parse_warnings[:50]

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
        "status": "success" if len(text.strip()) >= 10 else "failed",
        "extracted_json": extracted_json,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat(),
    }
    svc.table("extraction_runs").insert(run_row).execute()

    run_res = svc.table("extraction_runs").select("*").eq("id", run_id).maybe_single().execute()
    if run_res is None:
        raise HTTPException(status_code=500, detail="Gagal mengambil hasil ekstraksi")
    run = run_res.data
    return {"run": run, "inserted_materials": inserted}


@app.exception_handler(HTTPException)
def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
