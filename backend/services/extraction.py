from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

import fitz
from PIL import Image


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
    try:
        return float(raw.replace(",", "."))
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

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page_index in range(len(doc)):
        if len(rows) >= max_rows:
            break
        start_idx = len(rows)
        page = doc[page_index]
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
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []
    for page in doc:
        t = page.get_text("text") or ""
        if t.strip():
            parts.append(t)
    return "\n".join(parts)


def _try_import_pytesseract():
    try:
        import pytesseract
    except Exception:
        return None
    return pytesseract


def ocr_pdf_text(file_bytes: bytes, max_pages: int = 15) -> tuple[str, str | None]:
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        return "", "pytesseract tidak tersedia"

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    out: list[str] = []
    pages = min(len(doc), max_pages)

    for i in range(pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        try:
            txt = pytesseract.image_to_string(img)
        except Exception as e:
            return "\n".join(out), f"OCR gagal: {e}"
        if txt.strip():
            out.append(txt)

    return "\n".join(out), None


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
