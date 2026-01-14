# Materials: Ekstraksi & Tampilan

## Ringkasan
Sistem ini mengekstrak tabel material dari PDF, menyimpan hasilnya ke tabel `materials`, lalu menampilkannya dalam UI dengan pencarian, filter, sorting, dan pagination.

Target utama optimasi:
- Ekstraksi tabel yang stabil untuk format seperti `Daftar Material Terpasang.pdf`.
- Tampilan konsisten (Nama Item + Spesifikasi + Size + Quantity + Unit).
- Performansi baik untuk dataset besar dengan server-side pagination.

## Flowchart
```mermaid
flowchart TD
  A[User klik Ekstrak] --> B[Backend download PDF dari Supabase Storage]
  B --> C[Extract text via PyMuPDF]
  C --> D{Parse tabel dari PDF words?}
  D -->|Berhasil| E[parse_materials_from_pdf_bytes]
  D -->|Gagal / tidak ada words| F[parse_materials(text)]
  E --> G[Validasi & normalisasi field]
  F --> G
  G --> H[Hapus materials lama untuk document_id]
  H --> I[Insert materials baru]
  I --> J[Insert extraction_runs + metadata]
  J --> K[UI load materials via /materials/page]
```

## Spesifikasi Input
### Format PDF Tabel (Direkomendasikan)
PDF dengan layer teks dan header kolom:
- `ITEM` (angka urut)
- `QTY.`
- `UNIT`
- `SIZE`
- `DESCRIPTION`

Contoh row:
`1 16 M 4" PIPE, API 5L Gr.B, ERW, SCH.40, BE (ASME B36.10M)`

### Format OCR Spasi (Fallback)
Layout kolom dipisah beberapa spasi:
`Item   Size   Qty   Unit`

### Format Description-only (Fallback)
Baris hanya berisi description (tanpa qty/unit/size). Nilai yang tidak ada akan menjadi `null`.

## Output Data (Skema)
Setiap material disimpan ke kolom berikut:
- `description` (Nama Item)
- `spec` (Spesifikasi ringkas)
- `size`
- `quantity`
- `unit`
- `document_id`, `project_id`, `owner_id`, `created_at`

## Algoritma Ekstraksi
### 1) Parser PDF Words Table
Fungsi: `parse_materials_from_pdf_bytes(file_bytes, max_rows)`

Ringkasnya:
- Deteksi header tabel (`ITEM/QTY/UNIT/SIZE/DESCRIPTION`) dan posisi X masing-masing.
- Estimasi awal kolom `DESCRIPTION` dengan mencari kata pertama ber-huruf setelah kolom `SIZE`.
- Batasi area parsing (right boundary) untuk menghindari text title-block/legend.
- Untuk setiap `ITEM` yang terdeteksi (1..N):
  - Ambil band area di antara item sebelumnya & berikutnya.
  - Kelompokkan words ke kolom berdasarkan X.
  - Bentuk `qty/unit/size/description`.
  - Split `Nama Item` dan `Spesifikasi` dari `DESCRIPTION`.
  - Normalisasi unit dan size (mis. `4"` -> `4 Inch`).
  - Heuristik: jika `size` terlihat seperti berat (`14.5kg`) dan `unit` = `ea`, maka `unit` diset ke `14.5kg` dan `size` menjadi `null`.

### 2) Fallback Text Parser
Fungsi: `parse_materials(text, max_rows)`

Dipakai jika PDF tidak memiliki text-words yang bisa dipakai (scan/OCR) atau format tabel tidak terdeteksi.

## Validasi & Warning
Parser menghasilkan `warnings` bila:
- `description` kosong
- `qty` atau `unit` gagal terbaca
- `nama item` tidak terbaca

Warning disimpan pada `extraction_runs.notes` dan sebagian dimasukkan ke `extracted_json.warnings`.

## API untuk Tampilan (Pagination)
Endpoint:
- `GET /api/projects/{project_id}/materials/page`

Query params:
- `q`: pencarian (description/spec)
- `size`, `unit`: filter
- `sort_by`: `created_at|description|size|quantity|unit`
- `sort_dir`: `asc|desc`
- `limit`: 1..1000
- `offset`: >=0

Response:
- `items`: list material
- `offset`, `limit`
- `next_offset`: `null` jika tidak ada halaman berikutnya

## UI (Frontend)
Tabel Material menampilkan kolom:
1) Nama Item
2) Spesifikasi (bullet list)
3) Size
4) Quantity
5) Unit

Fitur:
- Sorting (klik header)
- Filter: `Cari`, `Size`, `Unit`
- Pagination: tombol `Muat lagi` (append hasil berikutnya)

## Panduan Maintenance
Checklist saat menambah format dokumen baru:
1) Pastikan header tabel bisa dideteksi atau tambahkan aturan deteksi baru.
2) Tambahkan unit test baru di `backend/tests/` (idealnya pakai sampel PDF).
3) Jalankan `py -3.12 -m unittest -q`.
4) Pastikan UI tetap konsisten: `description` singkat, detail di `spec`.

