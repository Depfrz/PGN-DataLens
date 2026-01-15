# Troubleshooting ekstraksi dokumen

Dokumen ini merangkum penyebab umum kegagalan ekstraksi dan mekanisme fallback yang tersedia.

## Gejala umum

### Status dokumen `failed`

Penyebab paling umum:
- PDF hasil scan tidak memiliki layer teks (hasil `extract_pdf_text` kosong)
- OCR belum tersedia (Tesseract belum terpasang / `TESSERACT_CMD` belum benar)
- File di Supabase Storage tidak ditemukan (404) atau akses signed URL gagal

## Mekanisme fallback

### PDF tanpa layer teks

Alur ekstraksi PDF:
- Coba ekstraksi teks dengan PyMuPDF
- Jika teks sangat pendek, jalankan OCR Tesseract
- Terlepas dari ada/tidaknya teks, sistem tetap mencoba parsing tabel material dari bytes PDF

Dokumen dianggap sukses jika salah satu terpenuhi:
- Teks hasil ekstraksi/OCR cukup (>= 10 karakter non-spasi), atau
- Parsing tabel material berhasil menghasilkan baris material

### Dokumen gambar

Endpoint ekstraksi umum hanya untuk PDF. Untuk dokumen gambar:
- Jalankan OCR MTO: `POST /api/documents/{document_id}/mto`
- Atau konversi ke PDF: `POST /api/documents/{document_id}/convert-to-pdf`

## Logging

Server akan menulis log exception untuk membantu diagnosa:
- `extract_pdf_text_failed`
- `ocr_pdf_text_failed`
- `parse_materials_from_pdf_bytes_failed`
- `extract_failed`

## Catatan integritas data

- File asli tidak diubah.
- Data `materials` untuk dokumen akan di-refresh (delete lalu insert) jika parsing material menghasilkan baris.

