from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel


DocumentStatus = Literal["uploaded", "extracting", "success", "failed"]
DocumentType = Literal["MRR", "MIR", "PipeBook", "BeritaAcara", "Sertifikat", "Lainnya"]
ExtractionMethod = Literal["pdf_text", "ocr", "pdf_text_then_ocr"]
ExtractionStatus = Literal["success", "failed"]


class AuthRequest(BaseModel):
    email: str
    password: str


class EmailRequest(BaseModel):
    email: str


class AuthSession(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user_id: str


class MeResponse(BaseModel):
    user_id: str


class EmailAvailabilityResponse(BaseModel):
    available: bool


class ProjectCreate(BaseModel):
    name: str
    location: str | None = None
    year: int | None = None
    status: Literal["Konstruksi", "Commissioning", "Gas In"] | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    year: int | None = None
    status: Literal["Konstruksi", "Commissioning", "Gas In"] | None = None
    description: str | None = None


class Project(BaseModel):
    id: str
    owner_id: str
    name: str
    location: str | None
    year: int | None
    status: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectWithSummary(Project):
    total_documents: int
    total_material_rows: int
    total_pipe_length_m: float


class Document(BaseModel):
    id: str
    project_id: str
    owner_id: str
    storage_path: str
    filename: str
    document_type: str
    document_number: str | None
    document_date: date | None
    status: DocumentStatus
    uploaded_at: datetime
    file_kind: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    original_filename: str | None = None
    download_url: str | None = None


class MaterialCreate(BaseModel):
    description: str
    size: str | None = None
    quantity: float | None = None
    unit: str | None = None
    heat_no: str | None = None
    tag_no: str | None = None
    spec: str | None = None
    document_id: str | None = None


class MaterialUpdate(BaseModel):
    description: str | None = None
    size: str | None = None
    quantity: float | None = None
    unit: str | None = None
    heat_no: str | None = None
    tag_no: str | None = None
    spec: str | None = None


class Material(BaseModel):
    id: str
    owner_id: str
    project_id: str
    document_id: str | None
    description: str
    size: str | None
    quantity: float | None
    unit: str | None
    heat_no: str | None
    tag_no: str | None
    spec: str | None
    created_at: datetime


class MaterialListResponse(BaseModel):
    items: list[Material]
    offset: int
    limit: int
    next_offset: int | None = None


class ExtractionRun(BaseModel):
    id: str
    owner_id: str
    document_id: str
    method: ExtractionMethod
    status: ExtractionStatus
    extracted_json: Any | None
    notes: str | None
    created_at: datetime


class ExtractionResponse(BaseModel):
    run: ExtractionRun
    inserted_materials: int
