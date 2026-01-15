from __future__ import annotations

import io
import os
import re
import logging
import shutil
from dataclasses import dataclass
from typing import Any, Protocol, cast
import importlib

try:
    _fitz = importlib.import_module("fitz")
except Exception:
    _fitz = None

fitz: Any = _fitz
from PIL import Image, ImageOps


def _require_fitz() -> Any:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) tidak tersedia")
    return fitz


_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_PDF_EXTS = {".pdf"}
_ALLOWED_PDF_MIMES = {"application/pdf"}

logger = logging.getLogger("pgn_datalens.extraction")


def _is_pdf_bytes(data: bytes) -> bool:
    if not data:
        return False
    head = data.lstrip()[:8]
    return head.startswith(b"%PDF-")


def _detect_image_format(data: bytes) -> tuple[str | None, int | None, int | None]:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return None, None, None
    fmt = (img.format or "").upper() or None
    w, h = img.size
    return fmt, int(w), int(h)


def detect_upload_kind(
    file_bytes: bytes,
    *,
    filename: str,
    content_type: str | None,
) -> str:
    name = (filename or "").strip()
    ext = ("." + name.split(".")[-1]).lower() if "." in name else ""
    ct = (content_type or "").strip().lower() or None

    pdf_sig = _is_pdf_bytes(file_bytes)
    img_fmt, _, _ = _detect_image_format(file_bytes)
    img_ok = img_fmt in {"PNG", "JPEG", "WEBP"}

    if ext in _ALLOWED_PDF_EXTS:
        if pdf_sig:
            return "pdf"
        raise ValueError("File berekstensi .pdf tetapi kontennya bukan PDF")

    if ext in _ALLOWED_IMAGE_EXTS:
        if img_ok:
            return "image"
        raise ValueError("File berekstensi gambar tetapi kontennya bukan JPEG/PNG/WEBP")

    if ext == "":
        if pdf_sig:
            return "pdf"
        if img_ok:
            return "image"
        if ct in _ALLOWED_PDF_MIMES:
            raise ValueError("MIME type application/pdf tetapi konten tidak terdeteksi sebagai PDF")
        if ct in _ALLOWED_IMAGE_MIMES:
            raise ValueError("MIME type gambar tetapi konten tidak terdeteksi sebagai JPEG/PNG/WEBP")
        raise ValueError("File tanpa ekstensi dan tipe file tidak dapat dideteksi")

    if pdf_sig:
        raise ValueError("Ekstensi file tidak sesuai: konten PDF tetapi ekstensi bukan .pdf")
    if img_ok:
        raise ValueError("Ekstensi file tidak sesuai: konten gambar tetapi ekstensi bukan .jpg/.jpeg/.png/.webp")
    raise ValueError("Format tidak didukung. Gunakan PDF/JPG/JPEG/PNG/WEBP")


class _MuPDFPage(Protocol):
    rect: Any

    def get_text(self, option: str, *args: Any, **kwargs: Any) -> Any: ...

    def get_pixmap(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass
class ExtractedDocInfo:
    document_type: str
    document_number: str | None
    sizes: list[str]


_RE_DOC_NUMBER = re.compile(r"\bPGAS-[A-Z0-9-]{6,}\b")
_RE_SIZE = re.compile(r"\b(\d+(?:\.\d+)?|\d+\/\d+)\s*(?:inch|in\b|\")", re.IGNORECASE)
_RE_QTY = re.compile(
    r"\b(?:qty|quantity|jumlah)\b\s*[:=]?\s*(\d+(?:[\.,]\d+)*)\s*(m|meter|meters|pcs|pc|set|joint|joints)?\b",
    re.IGNORECASE,
)
_RE_QTY_SIMPLE = re.compile(
    r"\b(\d+(?:[\.,]\d+)*)\b\s*(m|meter|meters|pcs|pc|set|joint|joints)\b",
    re.IGNORECASE,
)


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.strip().lower()
    if u in ["meter", "meters"]:
        return "m"
    if u in ["pc"]:
        return "pcs"
    if u in ["joints"]:
        return "joint"
    return u


def _parse_number(raw: str) -> float | None:
    if not raw:
        return None

    s = str(raw).strip()
    if not s:
        return None

    s = re.sub(r"[^0-9,\.\-+]", "", s)
    if not re.search(r"\d", s):
        return None

    last_dot = s.rfind(".")
    last_comma = s.rfind(",")

    if last_dot != -1 and last_comma != -1:
        decimal_sep = "." if last_dot > last_comma else ","
        thousand_sep = "," if decimal_sep == "." else "."
        s = s.replace(thousand_sep, "")
        s = s.replace(decimal_sep, ".")
    elif last_dot != -1:
        parts = s.split(".")
        if len(parts) >= 3:
            if all(len(p) == 3 for p in parts[1:]):
                s = "".join(parts)
            else:
                s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            a, b = parts[0], parts[1]
            if len(b) == 3 and len(a) <= 3:
                s = a + b
            else:
                s = a + "." + b
    elif last_comma != -1:
        parts = s.split(",")
        if len(parts) >= 3:
            if all(len(p) == 3 for p in parts[1:]):
                s = "".join(parts)
            else:
                s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            a, b = parts[0], parts[1]
            if len(b) == 3 and len(a) <= 3:
                s = a + b
            else:
                s = a + "." + b

    try:
        return float(s)
    except Exception:
        return None


def _has_alpha(s: str) -> bool:
    return any(ch.isalpha() for ch in s)


def _strip_size_qty_tokens(s: str) -> str:
    out = s
    out = _RE_SIZE.sub(" ", out)
    out = _RE_QTY.sub(" ", out)
    out = _RE_QTY_SIMPLE.sub(" ", out)
    out = re.sub(r"\b(inch|in)\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\b(pcs|pc|set|joint|joints|meter|meters|m)\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\b\d+(?:[\.,]\d+)?\b", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" -•|:\t")
    return out.strip()


def _is_noise_line(s: str) -> bool:
    t = s.strip().lower()
    if not t:
        return True
    if t in ["material terpasang", "materials", "material"]:
        return True
    if any(k in t for k in ["material", "description", "item", "size", "qty", "quantity", "unit", "heat", "no."]):
        return True
    if t in ["-", "--", "_"]:
        return True
    return False


def _split_item_name_and_spec(description: str) -> tuple[str, str | None]:
    d = (description or "").strip(" -•|:\t")
    if not d:
        return "", None

    if "," in d:
        head, tail = d.split(",", 1)
        name = head.strip()
        spec = tail.strip(" ,;:-\t")
    else:
        tokens = d.split()
        markers = {
            "api",
            "astm",
            "asme",
            "ansi",
            "jis",
            "din",
            "iso",
            "sch",
            "schedule",
            "gr",
            "grade",
            "dn",
            "pn",
            "ss",
            "cs",
            "smls",
            "erw",
            "bw",
            "be",
        }
        split_idx = None
        for i, tok in enumerate(tokens):
            t = tok.strip(" ,;:-()[]{}").lower()
            if tok.startswith("(") or tok.endswith(")") or "(" in tok or ")" in tok:
                split_idx = i
                break
            if t in markers:
                split_idx = i
                break
            if t.startswith("sch") and len(t) > 3:
                split_idx = i
                break
            if t.startswith("gr") and len(t) > 2:
                split_idx = i
                break

        if split_idx is None or split_idx == 0:
            name = d
            spec = ""
        else:
            name = " ".join(tokens[:split_idx]).strip()
            spec = " ".join(tokens[split_idx:]).strip(" ,;:-\t")

    if not _has_alpha(name) or len(name) < 2:
        return d, None
    return name, (spec if spec else None)


def _normalize_size_token(token: str) -> str | None:
    t = (token or "").strip()
    if not t:
        return None
    t = t.replace("—", "-")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("''", '"')
    if t in ["-", "--"]:
        return None

    m = re.fullmatch(r"(\d+(?:\.\d+)?|\d+\/\d+)\"", t)
    if m:
        return f"{m.group(1)} Inch"
    if any(ch in t.lower() for ch in ["x", "mm"]):
        return t
    m2 = _RE_SIZE.search(t)
    if m2:
        return f"{m2.group(1)} Inch"
    return t


def _parse_table_row_line(line: str) -> dict[str, Any] | None:
    ln = (line or "").strip().replace("—", "-")
    if not ln:
        return None
    parts = re.split(r"\s+", ln)
    if len(parts) < 5:
        return None
    if not re.fullmatch(r"\d+", parts[0]):
        return None
    if not re.fullmatch(r"\d+(?:[\.,]\d+)?", parts[1]):
        return None

    qty = _parse_number(parts[1])
    unit = _normalize_unit(parts[2]) or parts[2].strip().lower()
    size = _normalize_size_token(parts[3])
    desc = " ".join(parts[4:]).strip()
    if not desc or not _has_alpha(desc):
        return None

    return {"description": desc[:500], "quantity": qty, "unit": unit, "size": size}


def parse_materials_from_pdf_bytes(file_bytes: bytes, max_rows: int = 5000) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    _require_fitz()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page_index in range(len(doc)):
        if len(rows) >= max_rows:
            break
        start_idx = len(rows)
        page = cast(_MuPDFPage, doc[page_index])
        words = page.get_text("words") or []
        if not words:
            continue

        headers = [
            w
            for w in words
            if w[4].upper() in ["ITEM", "QTY.", "QTY", "UNIT", "SIZE", "DESCRIPTION"]
        ]
        table_hdr = None
        for w in headers:
            if w[4].upper() == "ITEM":
                y = w[1]
                line_headers = [h for h in headers if abs(h[1] - y) <= 2]
                labels = {h[4].upper() for h in line_headers}
                if {"ITEM", "UNIT", "SIZE", "DESCRIPTION"}.issubset(labels) and ("QTY." in labels or "QTY" in labels):
                    table_hdr = (y, line_headers)
                    break
        if table_hdr is None:
            continue

        header_y, line_headers = table_hdr
        xs = {h[4].upper(): h[0] for h in line_headers}
        item_x = xs.get("ITEM")
        qty_x = xs.get("QTY.") or xs.get("QTY")
        unit_x = xs.get("UNIT")
        size_x = xs.get("SIZE")
        desc_center_x = xs.get("DESCRIPTION")
        if item_x is None or qty_x is None or unit_x is None or size_x is None or desc_center_x is None:
            continue

        desc_start_x = None
        for x0, y0, x1, y1, txt, block, line, wn in words:
            if y0 <= header_y + 6:
                continue
            if y0 >= header_y + 220:
                continue
            if x0 <= size_x + 6:
                continue
            if not _has_alpha(txt):
                continue
            if desc_start_x is None or x0 < desc_start_x:
                desc_start_x = x0
        if desc_start_x is None:
            desc_start_x = max(size_x + 20, desc_center_x - 200)

        table_right_x = min(page.rect.width, desc_center_x + 320)

        b1 = (item_x + qty_x) / 2
        b2 = (qty_x + unit_x) / 2
        b3 = (unit_x + size_x) / 2
        b4 = (size_x + desc_start_x) / 2

        item_marks: list[tuple[int, float]] = []
        for x0, y0, x1, y1, txt, block, line, wn in words:
            if y0 <= header_y + 6:
                continue
            if x0 < item_x - 5 or x0 > item_x + 40:
                continue
            if re.fullmatch(r"\d+", txt):
                item_marks.append((int(txt), y0))
        item_marks = sorted(item_marks, key=lambda t: t[1])

        current = None
        for idx, (item_no, item_y) in enumerate(item_marks):
            if len(rows) >= max_rows:
                break
            prev_y = item_marks[idx - 1][1] if idx > 0 else header_y + 6
            next_y = item_marks[idx + 1][1] if idx + 1 < len(item_marks) else item_y + 50
            top = (prev_y + item_y) / 2 if idx > 0 else header_y + 6
            bottom = (item_y + next_y) / 2 if idx + 1 < len(item_marks) else item_y + 50

            cols: dict[str, list[tuple[float, float, str]]] = {"item": [], "qty": [], "unit": [], "size": [], "desc": []}
            for x0, y0, x1, y1, txt, block, line, wn in words:
                if y0 <= header_y + 6:
                    continue
                if y0 < top or y0 >= bottom:
                    continue
                if x0 < item_x - 20:
                    continue
                if x0 > table_right_x:
                    continue
                if x0 < b1:
                    cols["item"].append((y0, x0, txt))
                elif x0 < b2:
                    cols["qty"].append((y0, x0, txt))
                elif x0 < b3:
                    cols["unit"].append((y0, x0, txt))
                elif x0 < b4:
                    cols["size"].append((y0, x0, txt))
                else:
                    cols["desc"].append((y0, x0, txt))

            def _join_col(key: str) -> str:
                if not cols[key]:
                    return ""
                parts = sorted(cols[key])
                lines: list[str] = []
                current_y = None
                line_parts: list[tuple[float, str]] = []
                for y0, x0, txt in parts:
                    if current_y is None or abs(y0 - current_y) > 2.5:
                        if line_parts:
                            lines.append(" ".join(t for _, t in sorted(line_parts)))
                        current_y = y0
                        line_parts = [(x0, txt)]
                    else:
                        line_parts.append((x0, txt))
                if line_parts:
                    lines.append(" ".join(t for _, t in sorted(line_parts)))
                return " ".join(ln.strip() for ln in lines if ln.strip()).strip()

            item_s = _join_col("item")
            qty_s = _join_col("qty")
            unit_s = _join_col("unit")
            size_s = _join_col("size")
            desc_s = _join_col("desc")

            m_item = re.search(r"\b\d+\b", item_s)
            item_s = m_item.group(0) if m_item else ""

            if not item_s or not re.fullmatch(r"\d+", item_s):
                continue
            if int(item_s) != item_no:
                continue

            raw_desc = desc_s
            qty = _parse_number(qty_s)
            unit = _normalize_unit(unit_s) or (unit_s.lower() if unit_s else None)
            size = _normalize_size_token(size_s)

            if size and unit and unit.lower() in ["ea", "pcs"] and re.fullmatch(r"\d+(?:[\.,]\d+)?\s*kg", str(size).strip(), flags=re.IGNORECASE):
                unit = str(size).strip().lower().replace(" ", "")
                size = None

            if not raw_desc or not _has_alpha(raw_desc):
                warnings.append(f"page {page_index+1} row {item_s}: description kosong")
                continue

            name, spec_detail = _split_item_name_and_spec(raw_desc)
            if not name:
                warnings.append(f"page {page_index+1} row {item_s}: nama item tidak terbaca")
                continue
            spec = spec_detail

            if qty is None or unit is None:
                warnings.append(f"page {page_index+1} row {item_s}: qty/unit tidak terbaca")

            row = {
                "description": name[:500],
                "spec": spec[:500] if spec else None,
                "size": size,
                "quantity": qty,
                "unit": unit,
                "_raw_desc": raw_desc,
            }
            rows.append(row)
            current = row

        for r in rows[start_idx:]:
            raw = (r.get("_raw_desc") or "").strip()
            name, spec_detail = _split_item_name_and_spec(raw)
            if name:
                r["description"] = name[:500]
            if spec_detail:
                r["spec"] = spec_detail[:500]
            r.pop("_raw_desc", None)

    return rows[:max_rows], warnings


def _parse_spaced_columns_row_line(line: str) -> dict[str, Any] | None:
    ln = (line or "").strip().replace("—", "-")
    if not ln:
        return None
    parts = re.split(r"\s{2,}", ln)
    if len(parts) < 4:
        return None

    unit_raw = parts[-1].strip()
    qty_raw = parts[-2].strip()
    size_raw = parts[-3].strip()
    item_raw = " ".join(p.strip() for p in parts[:-3] if p.strip()).strip()

    if not item_raw or not _has_alpha(item_raw):
        return None
    if not re.fullmatch(r"\d+(?:[\.,]\d+)?", qty_raw):
        return None

    qty = _parse_number(qty_raw)
    unit = _normalize_unit(unit_raw) or unit_raw.lower()
    size = _normalize_size_token(size_raw)

    return {"description": item_raw[:500], "quantity": qty, "unit": unit, "size": size}


def _parse_right_anchored_row_line(line: str) -> dict[str, Any] | None:
    ln = (line or "").strip().replace("—", "-")
    if not ln:
        return None
    parts = re.split(r"\s+", ln)
    if len(parts) < 4:
        return None

    unit_raw = parts[-1]
    qty_raw = parts[-2]
    size_raw = parts[-3]
    item_raw = " ".join(parts[:-3]).strip()

    if not item_raw or not _has_alpha(item_raw):
        return None
    if not re.fullmatch(r"\d+(?:[\.,]\d+)?", qty_raw):
        return None
    if not re.fullmatch(r"[A-Za-z]{1,6}", unit_raw):
        return None

    qty = _parse_number(qty_raw)
    unit = _normalize_unit(unit_raw) or unit_raw.lower()
    size = _normalize_size_token(size_raw)
    return {"description": item_raw[:500], "quantity": qty, "unit": unit, "size": size}


def extract_pdf_text(file_bytes: bytes) -> str:
    if fitz is None:
        return ""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []
    for page in doc:
        t = cast(_MuPDFPage, page).get_text("text") or ""
        if t.strip():
            parts.append(t)
    return "\n".join(parts)


def _try_import_pytesseract():
    try:
        pytesseract = importlib.import_module("pytesseract")
    except Exception:
        return None

    cmd = (os.getenv("TESSERACT_CMD") or "").strip()
    if not cmd:
        cmd = shutil.which("tesseract") or ""
    if not cmd:
        for p in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(p):
                cmd = p
                break

    if cmd and os.path.exists(cmd):
        try:
            pytesseract.pytesseract.tesseract_cmd = cmd
        except Exception:
            pass
    return pytesseract


def validate_and_convert_image_upload(
    file_bytes: bytes,
    *,
    filename: str,
    content_type: str | None,
    max_bytes: int = 5 * 1024 * 1024,
    max_dim: int = 2000,
) -> tuple[bytes, int, int, str, str]:
    if not file_bytes:
        raise ValueError("File kosong")

    if len(file_bytes) > max_bytes:
        raise ValueError("Ukuran file melebihi 5MB")

    name = (filename or "").strip()
    ext = ("." + name.split(".")[-1]).lower() if "." in name else ""
    ct = (content_type or "").strip().lower() or None

    if ext and ext not in _ALLOWED_IMAGE_EXTS:
        raise ValueError("Format tidak didukung. Gunakan JPG/JPEG/PNG/WEBP")

    if ct and ct not in _ALLOWED_IMAGE_MIMES:
        raise ValueError("MIME type tidak didukung. Gunakan image/jpeg, image/png, atau image/webp")

    if ext and ct:
        mime_by_ext = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        expected = mime_by_ext.get(ext)
        if expected and ct != expected:
            raise ValueError(f"MIME type tidak sesuai dengan ekstensi file (diharapkan {expected})")

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Gagal membaca gambar: {e}")

    fmt_in = (img.format or "").upper()

    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        pass

    fmt = fmt_in or (img.format or "").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt not in {"PNG", "JPEG", "WEBP"}:
        raise ValueError("Format gambar tidak didukung. Gunakan JPG/JPEG/PNG/WEBP")

    try:
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
    except Exception:
        pass

    w, h = img.size
    out_w, out_h = int(w), int(h)
    if max_dim and (out_w > max_dim or out_h > max_dim):
        scale = min(max_dim / max(1, out_w), max_dim / max(1, out_h))
        new_w = max(1, int(round(out_w * scale)))
        new_h = max(1, int(round(out_h * scale)))
        try:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except Exception:
            img = img.resize((new_w, new_h))
        out_w, out_h = new_w, new_h

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")

    buf = io.BytesIO()
    out_mime = "image/png"
    out_ext = ".png"
    try:
        if fmt == "PNG" or img.mode == "RGBA":
            img.save(buf, format="PNG", optimize=True, compress_level=9)
            out_mime = "image/png"
            out_ext = ".png"
        else:
            img_rgb = img.convert("RGB")
            img_rgb.save(buf, format="JPEG", quality=88, optimize=True, progressive=True)
            out_mime = "image/jpeg"
            out_ext = ".jpg"
    except Exception as e:
        raise ValueError(f"Konversi gambar gagal: {e}")

    out = buf.getvalue()
    if len(out) > max_bytes:
        if out_mime == "image/jpeg":
            for q in (80, 72, 65):
                buf = io.BytesIO()
                try:
                    img.convert("RGB").save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
                except Exception:
                    continue
                out = buf.getvalue()
                if len(out) <= max_bytes:
                    break
        else:
            try:
                bg = Image.new("RGB", img.size, color=(255, 255, 255))
                bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                buf = io.BytesIO()
                bg.save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
                out = buf.getvalue()
                out_mime = "image/jpeg"
                out_ext = ".jpg"
            except Exception:
                pass

        if len(out) > max_bytes:
            raise ValueError("Ukuran file melebihi 5MB setelah konversi")

    return out, int(out_w), int(out_h), out_mime, out_ext


def convert_image_bytes_to_pdf(image_bytes: bytes) -> bytes:
    if not image_bytes:
        raise ValueError("File kosong")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Gagal membaca gambar: {e}")

    frames: list[Image.Image] = []
    try:
        n = int(getattr(img, "n_frames", 1) or 1)
    except Exception:
        n = 1
    for i in range(max(1, n)):
        try:
            if n > 1:
                img.seek(i)
        except Exception:
            break
        fr = img.convert("RGB")
        frames.append(fr)

    if not frames:
        raise ValueError("Gagal membaca frame gambar")

    buf = io.BytesIO()
    if len(frames) == 1:
        frames[0].save(buf, format="PDF", resolution=300.0)
    else:
        frames[0].save(buf, format="PDF", save_all=True, append_images=frames[1:], resolution=300.0)
    return buf.getvalue()


def extract_mto_from_image_bytes_advanced(
    image_bytes: bytes,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    split_columns: bool | None = None,
    threshold: int = 185,
    deskew: bool = True,
) -> list[dict[str, Any]]:
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        raise RuntimeError("pytesseract tidak tersedia")
    _ensure_tesseract_ready(pytesseract)

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Gagal membaca gambar: {e}")

    try:
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
    except Exception:
        pass

    page_img = img.convert("RGB")
    crop_img = page_img

    if bbox is None:
        small = page_img.resize((max(1, page_img.size[0] // 2), max(1, page_img.size[1] // 2)))
        small_pp = _preprocess_for_ocr(small, threshold=min(210, threshold + 10), upscale=1.0)
        if deskew:
            small_pp = _maybe_rotate_with_osd(pytesseract, small_pp)
        tokens_small = _image_to_tokens(pytesseract, small_pp, psm=6)
        found = _find_mto_bbox_from_tokens(tokens_small, small.size[0], small.size[1])
        if found is not None:
            x0, y0, x1, y1 = found
            scale_x = page_img.size[0] / small.size[0]
            scale_y = page_img.size[1] / small.size[1]
            bbox = (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y)

    if bbox is not None:
        x0, y0, x1, y1 = bbox
        x0i = max(0, min(page_img.size[0], int(x0)))
        y0i = max(0, min(page_img.size[1], int(y0)))
        x1i = max(0, min(page_img.size[0], int(x1)))
        y1i = max(0, min(page_img.size[1], int(y1)))
        if x1i - x0i >= 10 and y1i - y0i >= 10:
            crop_img = page_img.crop((x0i, y0i, x1i, y1i))

    pp = _preprocess_for_ocr(crop_img, threshold=threshold, upscale=2.0)
    if deskew:
        pp = _maybe_rotate_with_osd(pytesseract, pp)

    tokens = _image_to_tokens(pytesseract, pp, psm=6)
    w, h = pp.size
    split = split_columns if split_columns is not None else _split_columns_if_needed(tokens, w)
    if not split:
        return _tokens_to_rows(tokens, w, h, source="source=image")

    mid = w // 2
    left_img = pp.crop((0, 0, mid, h))
    right_img = pp.crop((mid, 0, w, h))
    left_tokens = _image_to_tokens(pytesseract, left_img, psm=6)
    right_tokens = _image_to_tokens(pytesseract, right_img, psm=6)
    left_rows = _tokens_to_rows(left_tokens, left_img.size[0], left_img.size[1], source="source=image,side=left")
    right_rows = _tokens_to_rows(right_tokens, right_img.size[0], right_img.size[1], source="source=image,side=right")
    merged: dict[int, dict[str, Any]] = {}
    for r in left_rows + right_rows:
        k = int(r["item"])
        prev = merged.get(k)
        if prev is None:
            merged[k] = r
            continue
        for kk in ["material", "description", "nps", "qty_value", "qty_unit"]:
            if prev.get(kk) in (None, "") and r.get(kk) not in (None, ""):
                prev[kk] = r.get(kk)
    return [merged[k] for k in sorted(merged.keys())]


def ocr_pdf_text(file_bytes: bytes, max_pages: int = 15) -> tuple[str, str | None]:
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        return "", "pytesseract tidak tersedia"

    if fitz is None:
        return "", "PyMuPDF (fitz) tidak tersedia"

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    out: list[str] = []
    pages = min(len(doc), max_pages)

    for i in range(pages):
        page = cast(_MuPDFPage, doc[i])
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        try:
            txt = pytesseract.image_to_string(img)
        except Exception as e:
            return "\n".join(out), f"OCR gagal: {e}"
        if txt.strip():
            out.append(txt)

    return "\n".join(out), None


@dataclass(frozen=True)
class _OCRToken:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: int

    @property
    def x_center(self) -> float:
        return self.x + (self.w / 2.0)

    @property
    def y_center(self) -> float:
        return self.y + (self.h / 2.0)


def _ensure_tesseract_ready(pytesseract) -> None:
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(
            "Tesseract OCR tidak terdeteksi. Install Tesseract dan pastikan tesseract.exe ada di PATH, "
            "atau set env TESSERACT_CMD ke path tesseract.exe."
        ) from e


def _render_pdf_page_to_image(pdf_bytes: bytes, page_index: int, dpi: int) -> Image.Image:
    _require_fitz()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_index < 0 or page_index >= len(doc):
        raise ValueError(f"page_index di luar range: {page_index} (pages={len(doc)})")

    page = cast(_MuPDFPage, doc[page_index])
    zoom = max(1.0, float(dpi) / 72.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return img


def _preprocess_for_ocr(img: Image.Image, *, threshold: int = 185, upscale: float = 2.0) -> Image.Image:
    g = img.convert("L")
    g = ImageOps.autocontrast(g)
    if upscale and upscale != 1.0:
        w, h = g.size
        g = g.resize((max(1, int(w * upscale)), max(1, int(h * upscale))), resample=Image.Resampling.LANCZOS)
    thr = int(threshold)
    def _thr_fn(v: int) -> int:
        return 255 if v >= thr else 0
    bw = g.point(_thr_fn)
    return bw


def _maybe_rotate_with_osd(pytesseract, img: Image.Image) -> Image.Image:
    try:
        osd = pytesseract.image_to_osd(img)
    except Exception:
        return img

    m = re.search(r"Rotate:\s*(\d+)", osd)
    if not m:
        return img
    deg = int(m.group(1))
    if deg not in (90, 180, 270):
        return img
    return img.rotate(-deg, expand=True)


def _image_to_tokens(pytesseract, img: Image.Image, *, psm: int = 6, lang: str = "eng") -> list[_OCRToken]:
    Output = getattr(pytesseract, "Output", None)
    if Output is None:
        raise RuntimeError("pytesseract Output tidak tersedia")

    data = pytesseract.image_to_data(
        img,
        output_type=Output.DICT,
        lang=lang,
        config=f"--oem 3 --psm {int(psm)}",
    )
    n = len(data.get("text", []) or [])
    out: list[_OCRToken] = []
    for i in range(n):
        txt = str((data.get("text") or [""])[i]).strip()
        if not txt:
            continue
        try:
            conf = int(float((data.get("conf") or ["-1"])[i]))
        except Exception:
            conf = -1
        try:
            x = int((data.get("left") or [0])[i])
            y = int((data.get("top") or [0])[i])
            w = int((data.get("width") or [0])[i])
            h = int((data.get("height") or [0])[i])
        except Exception:
            continue
        out.append(_OCRToken(text=txt, x=x, y=y, w=w, h=h, conf=conf))
    return out


def _find_mto_bbox_from_tokens(tokens: list[_OCRToken], img_w: int, img_h: int) -> tuple[int, int, int, int] | None:
    if not tokens:
        return None
    tks = [t for t in tokens if t.conf >= 20]
    if not tks:
        return None

    upper = [t.text.upper() for t in tks]
    best: tuple[int, int, int, int] | None = None

    def _set_best(y_bottom: int):
        nonlocal best
        top = max(0, min(img_h - 1, y_bottom + int(img_h * 0.01)))
        best = (0, top, img_w, img_h)

    for i, u in enumerate(upper):
        if u == "MTO":
            _set_best(tks[i].y + tks[i].h)
            break

    if best is not None:
        return best

    def _norm(s: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", (s or "").upper())

    normed = [_norm(t.text) for t in tks]
    for i, nu in enumerate(normed):
        if nu not in ("MATERIALS", "MATERIAL"):
            continue
        y = tks[i].y_center
        seen_take = False
        seen_takes = False
        seen_off = False
        y_bottom = tks[i].y + tks[i].h
        for ii in range(i + 1, min(i + 10, len(tks))):
            if abs(tks[ii].y_center - y) > 30:
                continue
            n2 = normed[ii]
            if n2 == "TAKE":
                seen_take = True
                y_bottom = max(y_bottom, tks[ii].y + tks[ii].h)
            elif n2 == "TAKES":
                seen_takes = True
                y_bottom = max(y_bottom, tks[ii].y + tks[ii].h)
            elif n2 == "OFF":
                seen_off = True
                y_bottom = max(y_bottom, tks[ii].y + tks[ii].h)
        if (seen_take or seen_takes) and seen_off:
            _set_best(y_bottom)
            return best

    return None


def _split_columns_if_needed(tokens: list[_OCRToken], img_w: int) -> bool:
    items = []
    for t in tokens:
        if t.conf < 40:
            continue
        if not re.fullmatch(r"\d{1,3}", t.text):
            continue
        try:
            v = int(t.text)
        except Exception:
            continue
        if 1 <= v <= 500:
            items.append(t)

    if len(items) < 8:
        return False

    left = sum(1 for t in items if t.x < int(img_w * 0.45))
    right = sum(1 for t in items if t.x > int(img_w * 0.55))
    return left >= 3 and right >= 3


def _compute_column_bounds(tokens: list[_OCRToken], img_w: int, img_h: int) -> dict[str, int]:
    default = {
        "item_end": int(img_w * 0.12),
        "material_end": int(img_w * 0.26),
        "description_end": int(img_w * 0.74),
        "nps_end": int(img_w * 0.86),
        "qty_end": img_w,
    }
    if not tokens:
        return default

    header = [t for t in tokens if t.conf >= 15 and t.y < int(img_h * 0.25)]
    if not header:
        return default

    def _norm_label(s: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "", (s or "").upper())

    header_norm = [(_norm_label(t.text), t) for t in header]

    def _center_for_any(labels: list[str]) -> float | None:
        want = {_norm_label(l) for l in labels}
        cands = [t for (n, t) in header_norm if n in want]
        if not cands:
            return None
        t = min(cands, key=lambda x: x.y)
        return t.x_center

    item_c = _center_for_any(["ITEM", "NO", "NO.", "NUMBER"]) 
    mat_c = _center_for_any(["MATERIAL", "MATL"]) 
    desc_c = _center_for_any(["DESCRIPTION", "DESC"]) 
    nps_c = _center_for_any(["NPS"]) 
    qty_c = _center_for_any(["QTY", "QUANTITY", "Q'TY", "QT'Y", "QTY."])

    bounds = dict(default)
    if item_c is not None and mat_c is not None:
        bounds["item_end"] = int((item_c + mat_c) / 2)
    if mat_c is not None and desc_c is not None:
        bounds["material_end"] = int((mat_c + desc_c) / 2)
    if desc_c is not None and nps_c is not None:
        bounds["description_end"] = int((desc_c + nps_c) / 2)
    if nps_c is not None and qty_c is not None:
        bounds["nps_end"] = int((nps_c + qty_c) / 2)
    return bounds


def _parse_qty(text: str) -> tuple[float | None, str | None]:
    t = (text or "").strip()
    if not t:
        return None, None
    m = re.search(r"([-+]?\d[\d\.,]*)\s*([A-Za-z]{1,6})?", t)
    if not m:
        return None, None
    num = _parse_number(m.group(1) or "")
    unit = (m.group(2) or "").strip() or None
    if unit is not None:
        unit = unit.lower()
    return num, unit


def _tokens_to_rows(tokens: list[_OCRToken], img_w: int, img_h: int, *, source: str) -> list[dict[str, Any]]:
    clean = [t for t in tokens if t.conf >= 30 and t.text.strip()]
    if not clean:
        return []

    bounds = _compute_column_bounds(clean, img_w, img_h)
    item_end = bounds["item_end"]

    items = []
    for t in clean:
        if t.x >= item_end:
            continue
        if not re.fullmatch(r"\d{1,3}", t.text):
            continue
        try:
            v = int(t.text)
        except Exception:
            continue
        if 1 <= v <= 999:
            items.append((v, t))

    if not items:
        return []

    items.sort(key=lambda it: (it[1].y, it[1].x))
    anchors: list[tuple[int, _OCRToken]] = []
    for v, t in items:
        if not anchors:
            anchors.append((v, t))
            continue
        _, last = anchors[-1]
        if abs(t.y_center - last.y_center) <= max(12, int(last.h * 0.8)):
            if t.x < last.x or (t.conf > last.conf and abs(t.x - last.x) <= 6):
                anchors[-1] = (v, t)
            continue
        anchors.append((v, t))

    rows: list[dict[str, Any]] = []
    for idx, (item_no, anchor) in enumerate(anchors):
        y_top = max(0, int(anchor.y - anchor.h * 0.6))
        if idx + 1 < len(anchors):
            next_anchor = anchors[idx + 1][1]
            y_bottom = max(y_top + 1, int(next_anchor.y - next_anchor.h * 0.6))
        else:
            y_bottom = min(img_h, int(anchor.y + anchor.h * 4.0))
        if y_bottom <= y_top:
            continue

        band = [t for t in clean if (y_top <= t.y_center < y_bottom)]
        cols: dict[str, list[_OCRToken]] = {
            "material": [],
            "description": [],
            "nps": [],
            "qty": [],
        }

        for t in band:
            if t is anchor:
                continue
            x = t.x_center
            if x < item_end:
                continue
            if x < bounds["material_end"]:
                cols["material"].append(t)
            elif x < bounds["description_end"]:
                cols["description"].append(t)
            elif x < bounds["nps_end"]:
                cols["nps"].append(t)
            else:
                cols["qty"].append(t)

        def _join(ts: list[_OCRToken]) -> str:
            ts2 = sorted(ts, key=lambda z: (z.y, z.x))
            return " ".join(x.text for x in ts2).strip()

        material = _join(cols["material"]) or None
        description = _join(cols["description"]) or None
        nps = _join(cols["nps"]) or None
        qty_raw = _join(cols["qty"]) or ""
        qty_value, qty_unit = _parse_qty(qty_raw)

        rows.append(
            {
                "item": int(item_no),
                "material": material,
                "description": description,
                "nps": nps,
                "qty_value": qty_value,
                "qty_unit": qty_unit,
                "source": source,
            }
        )

    dedup: dict[int, dict[str, Any]] = {}
    for r in rows:
        key = int(r["item"])
        prev = dedup.get(key)
        if prev is None:
            dedup[key] = r
            continue
        for k in ["material", "description", "nps", "qty_value", "qty_unit"]:
            if prev.get(k) in (None, "") and r.get(k) not in (None, ""):
                prev[k] = r.get(k)

    return [dedup[k] for k in sorted(dedup.keys())]


def extract_mto_from_pdf_bytes(pdf_bytes: bytes, page_index: int) -> list[dict[str, Any]]:
    return extract_mto_from_pdf_bytes_advanced(pdf_bytes, page_index, bbox=None, split_columns=None)


def extract_mto_from_pdf_bytes_advanced(
    pdf_bytes: bytes,
    page_index: int,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    split_columns: bool | None = None,
    dpi: int = 500,
    threshold: int = 185,
    deskew: bool = True,
) -> list[dict[str, Any]]:
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        raise RuntimeError("pytesseract tidak tersedia")
    _ensure_tesseract_ready(pytesseract)

    page_img = _render_pdf_page_to_image(pdf_bytes, page_index, dpi)

    crop_img = page_img
    if bbox is None:
        small = page_img.resize((max(1, page_img.size[0] // 2), max(1, page_img.size[1] // 2)))
        small_pp = _preprocess_for_ocr(small, threshold=min(210, threshold + 10), upscale=1.0)
        if deskew:
            small_pp = _maybe_rotate_with_osd(pytesseract, small_pp)
        tokens_small = _image_to_tokens(pytesseract, small_pp, psm=6)
        found = _find_mto_bbox_from_tokens(tokens_small, small.size[0], small.size[1])
        if found is not None:
            x0, y0, x1, y1 = found
            scale_x = page_img.size[0] / small.size[0]
            scale_y = page_img.size[1] / small.size[1]
            bbox = (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y)

    if bbox is not None:
        x0, y0, x1, y1 = bbox
        x0i = max(0, min(page_img.size[0], int(x0)))
        y0i = max(0, min(page_img.size[1], int(y0)))
        x1i = max(0, min(page_img.size[0], int(x1)))
        y1i = max(0, min(page_img.size[1], int(y1)))
        if x1i - x0i >= 10 and y1i - y0i >= 10:
            crop_img = page_img.crop((x0i, y0i, x1i, y1i))

    pp = _preprocess_for_ocr(crop_img, threshold=threshold, upscale=2.0)
    if deskew:
        pp = _maybe_rotate_with_osd(pytesseract, pp)

    tokens = _image_to_tokens(pytesseract, pp, psm=6)
    w, h = pp.size

    split = split_columns if split_columns is not None else _split_columns_if_needed(tokens, w)
    if not split:
        return _tokens_to_rows(tokens, w, h, source=f"page={page_index + 1}")

    mid = w // 2
    left_img = pp.crop((0, 0, mid, h))
    right_img = pp.crop((mid, 0, w, h))
    left_tokens = _image_to_tokens(pytesseract, left_img, psm=6)
    right_tokens = _image_to_tokens(pytesseract, right_img, psm=6)

    left_rows = _tokens_to_rows(left_tokens, left_img.size[0], left_img.size[1], source=f"page={page_index + 1},side=left")
    right_rows = _tokens_to_rows(right_tokens, right_img.size[0], right_img.size[1], source=f"page={page_index + 1},side=right")
    merged: dict[int, dict[str, Any]] = {}
    for r in left_rows + right_rows:
        k = int(r["item"])
        prev = merged.get(k)
        if prev is None:
            merged[k] = r
            continue
        for kk in ["material", "description", "nps", "qty_value", "qty_unit"]:
            if prev.get(kk) in (None, "") and r.get(kk) not in (None, ""):
                prev[kk] = r.get(kk)
    return [merged[k] for k in sorted(merged.keys())]


def detect_document_type(text: str) -> str:
    t = text.lower()
    if "pipe book" in t or "pipebook" in t:
        return "PipeBook"
    if "mrr" in t or "material receipt" in t:
        return "MRR"
    if "mir" in t or "material inspection" in t:
        return "MIR"
    if "berita acara" in t or "ba " in t:
        return "BeritaAcara"
    if "sertifikat" in t or "certificate" in t:
        return "Sertifikat"
    return "Lainnya"


def parse_doc_info(text: str) -> ExtractedDocInfo:
    doc_no = None
    m = _RE_DOC_NUMBER.search(text)
    if m:
        doc_no = m.group(0)

    sizes: list[str] = []
    for size in _RE_SIZE.findall(text):
        sizes.append(f"{size} Inch")
    sizes = sorted(set(sizes))

    return ExtractedDocInfo(
        document_type=detect_document_type(text),
        document_number=doc_no,
        sizes=sizes,
    )


def parse_materials(text: str, max_rows: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    last_name_line: str | None = None
    seen: set[tuple[Any, ...]] = set()

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if len(rows) >= max_rows:
            break

        spaced_row = _parse_spaced_columns_row_line(ln)
        if spaced_row is None:
            spaced_row = _parse_right_anchored_row_line(ln)
        if spaced_row is not None:
            description = spaced_row["description"]
            size = spaced_row.get("size")
            quantity = spaced_row.get("quantity")
            unit = spaced_row.get("unit")

            name, spec_detail = _split_item_name_and_spec(description)
            if not name:
                continue
            spec = spec_detail

            key = (name.lower(), size, quantity, unit, (spec or "").lower())
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "description": name[:500],
                    "spec": spec[:500] if spec else None,
                    "size": size,
                    "quantity": quantity,
                    "unit": unit,
                }
            )
            last_name_line = None
            continue

        if _is_noise_line(ln):
            continue

        table_row = _parse_table_row_line(ln)
        if table_row is not None:
            description = table_row["description"]
            size = table_row.get("size")
            quantity = table_row.get("quantity")
            unit = table_row.get("unit")

            name, spec_detail = _split_item_name_and_spec(description)
            if not name:
                continue
            spec = spec_detail

            key = (name.lower(), size, quantity, unit, (spec or "").lower())
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "description": name[:500],
                    "spec": spec[:500] if spec else None,
                    "size": size,
                    "quantity": quantity,
                    "unit": unit,
                }
            )
            last_name_line = None
            continue

        only_number = re.fullmatch(r"\d+(?:[\.,]\d+)?", ln)
        only_unit = re.fullmatch(r"(?:m|meter|meters|pcs|pc|set|joint|joints)", ln.strip(), flags=re.IGNORECASE)
        if rows and (only_number or only_unit):
            prev = rows[-1]
            if only_number and prev.get("quantity") is None:
                q = _parse_number(ln)
                if q is not None:
                    prev["quantity"] = q
                    continue
            if only_unit and prev.get("quantity") is not None and prev.get("unit") is None:
                prev["unit"] = _normalize_unit(ln)
                continue

        if not _is_noise_line(ln) and _has_alpha(ln):
            candidate = _strip_size_qty_tokens(ln)
            if candidate and _has_alpha(candidate):
                last_name_line = candidate[:500]

        size_m = _RE_SIZE.search(ln)
        qty_m = _RE_QTY.search(ln)
        qty2_m = None if qty_m else _RE_QTY_SIMPLE.search(ln)

        size = f"{size_m.group(1)} Inch" if size_m else None
        quantity = None
        unit = None
        if qty_m:
            quantity = _parse_number(qty_m.group(1))
            unit = _normalize_unit(qty_m.group(2))
        elif qty2_m:
            quantity = _parse_number(qty2_m.group(1))
            unit = _normalize_unit(qty2_m.group(2))

        has_measure = size is not None or quantity is not None

        cleaned = _strip_size_qty_tokens(ln)
        spec = None
        description = None
        if cleaned and _has_alpha(cleaned):
            description = cleaned
            spec = None
        else:
            description = last_name_line
            spec = ln

        if not has_measure and description is None:
            continue

        if not description:
            continue

        name, spec_detail = _split_item_name_and_spec(description)
        if not name:
            continue
        description = name
        if spec_detail:
            spec = spec_detail if not spec else f"{spec_detail} | {spec}"

        merged = False
        if rows:
            prev = rows[-1]
            same_desc = (prev.get("description") or "").strip().lower() == description.strip().lower()
            if same_desc and not has_measure:
                if spec and spec != prev.get("spec"):
                    if prev.get("spec"):
                        joined = f"{prev['spec']} | {spec}"
                        prev["spec"] = joined[:500]
                    else:
                        prev["spec"] = spec[:500]
                merged = True
            elif same_desc:
                if prev.get("size") is None and size is not None:
                    prev["size"] = size
                    merged = True
                if prev.get("quantity") is None and quantity is not None:
                    prev["quantity"] = quantity
                    if prev.get("unit") is None:
                        prev["unit"] = unit
                    merged = True
                if prev.get("unit") is None and unit is not None and prev.get("quantity") is not None:
                    prev["unit"] = unit
                    merged = True
                if spec and spec != prev.get("spec"):
                    if prev.get("spec"):
                        joined = f"{prev['spec']} | {spec}"
                        prev["spec"] = joined[:500]
                    else:
                        prev["spec"] = spec[:500]
                    merged = True

                if not merged and has_measure:
                    same_size = size is None or prev.get("size") == size
                    same_qty = quantity is None or prev.get("quantity") == quantity
                    same_unit = unit is None or prev.get("unit") == unit
                    same_spec = spec is None or prev.get("spec") == spec
                    if same_size and same_qty and same_unit and same_spec:
                        merged = True

        if merged:
            continue

        key = (description.lower(), size, quantity, unit, (spec or "").lower())
        if key in seen:
            continue
        seen.add(key)

        rows.append(
            {
                "description": description[:500],
                "spec": spec[:500] if spec else None,
                "size": size,
                "quantity": quantity,
                "unit": unit,
            }
        )

    return rows


def build_extracted_json(text: str, method: str, notes: str | None = None) -> dict[str, Any]:
    info = parse_doc_info(text)
    materials_preview = parse_materials(text, max_rows=20)
    return {
        "method": method,
        "notes": notes,
        "document_type": info.document_type,
        "document_number": info.document_number,
        "sizes": info.sizes,
        "materials_preview": materials_preview,
        "text_length": len(text),
    }
