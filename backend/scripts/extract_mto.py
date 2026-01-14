from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from backend.services.extraction import extract_mto_from_pdf_bytes_advanced


def _parse_bbox(s: str | None):
    if not s:
        return None
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox harus format x0,y0,x1,y1")
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=str)
    ap.add_argument("--page-index", type=int, default=5)
    ap.add_argument("--bbox", type=str, default=None)
    ap.add_argument("--split-columns", action="store_true")
    ap.add_argument("--csv", type=str, default=None)
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    pdf_bytes = pdf_path.read_bytes()
    rows = extract_mto_from_pdf_bytes_advanced(
        pdf_bytes,
        int(args.page_index),
        bbox=_parse_bbox(args.bbox),
        split_columns=True if args.split_columns else None,
    )

    if args.csv:
        out_path = Path(args.csv)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["item", "material", "description", "nps", "qty_value", "qty_unit", "source"],
                extrasaction="ignore",
            )
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return 0

    print(json.dumps({"items": rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

