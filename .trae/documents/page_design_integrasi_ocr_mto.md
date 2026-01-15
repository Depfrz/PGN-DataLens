# Desain Halaman — Integrasi OCR MTO (Desktop-first)

## Global Styles (Design Tokens)
- Layout: max-width 1280px, grid 12 kolom, gutter 24px, container center.
- Warna:
  - Background: #0B1220 (dark) atau #FFFFFF (light), gunakan 1 tema konsisten dengan DataLens.
  - Primary: #2563EB, Success: #16A34A, Warning: #F59E0B, Danger: #DC2626.
  - Highlight compare: + (OCR berbeda) #FEF3C7, - (nilai lama) #E5E7EB.
- Tipografi: Inter/Roboto; scale 12/14/16/20/24.
- Komponen:
  - Button: primary/secondary/ghost; hover +8% brightness; disabled 40% opacity.
  - Badge status: Draft/Perlu Review/Disetujui/Ditolak.
  - Tabel: header sticky, zebra rows, inline edit dengan input ringkas.
- Responsif: desktop-first; di <1024px panel kanan (OCR) menjadi drawer; tabel jadi stacked rows.

---

## 1) Halaman: Tampilan Data (Detail MTO)

### Meta Information
- Title: "Tampilan Data MTO — Compare OCR"
- Description: "Bandingkan hasil OCR dengan data MTO, verifikasi, dan simpan dengan histori."
- Open Graph: og:title sama, og:type=website.

### Layout
- Struktur 2 panel (split-view) menggunakan CSS Grid:
  - Kiri (8 kolom): Data MTO (source of truth) + tabel line item.
  - Kanan (4 kolom): Panel OCR (hasil ekstraksi + confidence + aksi terima).
- Header sticky di atas (tinggi 56–64px) + toolbar aksi.

### Page Structure
1. Top App Bar
2. Dokumen Summary Card
3. Main Split View (Data vs OCR)
4. Footer Actions (sticky bottom di area konten)

### Sections & Components
1) **Top App Bar**
- Elemen: breadcrumb (Data → MTO → {docId}), status dokumen, tombol: "Import/Link OCR", "Ajukan Review", "Simpan".
- State: tombol "Simpan" aktif bila ada perubahan draft.

2) **Dokumen Summary Card**
- Field: doc_no, judul, sumber file, last OCR run, jumlah item, jumlah flagged.
- Komponen: mini-timeline (Last updated), link ke Histori.

3) **Panel Kiri — Tabel Data MTO**
- Tabel line item dengan kolom minimum: Line, Nama Item, Spesifikasi (expand), Size, Quantity, Unit, Status.
- Interaksi:
  - Klik baris membuka "Item Detail Drawer" (di kanan bawah panel kiri) untuk inline edit per-field.
  - Indikator perubahan: icon dot + tooltip "Ada usulan OCR".

4) **Panel Kanan — OCR Compare Panel**
- Untuk item terpilih:
  - Blok per-field: label field, nilai OCR (dengan confidence), nilai saat ini, tombol: "Terima OCR" / "Pertahankan".
  - Spesifikasi ditampilkan sebagai list multi-line (sesuai OCR) + tombol "Normalize" (mis. join baris; tetap menyimpan raw).
  - Warning list: confidence rendah, format quantity salah, unit tidak dikenali.
  - (Opsional) "Preview lokasi" jika bbox_map tersedia: thumbnail halaman + highlight area.

5) **Footer Actions**
- Tombol: "Terima semua perubahan item", "Tandai butuh review", "Simpan".
- Konfirmasi sebelum simpan: ringkasan field yang berubah.

### Interaction States
- Confidence threshold: <0.80 badge "Low" + auto-flag.
- Konflik: jika nilai data sudah berubah setelah OCR run, tampilkan banner "Data berubah, cek ulang".
- Validasi: inline error (merah) + helper text.

---

## 2) Halaman: Antrian Review OCR

### Meta Information
- Title: "Antrian Review OCR"
- Description: "Review item MTO yang ditandai untuk verifikasi OCR."

### Layout
- 2 kolom: kiri daftar (list/table) + kanan detail review (panel).
- Grid + sticky filter bar.

### Page Structure
1. Filter Bar
2. Review List
3. Review Detail Panel

### Sections & Components
1) **Filter Bar**
- Filter: dokumen, tanggal OCR run, status (Perlu Review), jenis flag (low confidence/format/konflik), search.

2) **Review List (Table)**
- Kolom: Doc No, Line, Field bermasalah (chips), Confidence min, Updated, Assignee (opsional), Aksi.
- Aksi cepat: "Approve" / "Reject" (membuka modal catatan jika reject).

3) **Review Detail Panel**
- Menampilkan compare per-field seperti halaman Detail, namun fokus pada field flagged.
- Tombol batch: "Approve & Next", "Reject & Next".

### Interaction States
- Keyboard shortcut (opsional): J/K navigasi item, A approve, R reject.

---

## 3) Halaman: Histori Perubahan

### Meta Information
- Title: "Histori Perubahan MTO"
- Description: "Audit trail perubahan data MTO dari OCR dan manual."

### Layout
- 3 area: kiri filter + list revisi, tengah detail revisi, kanan konteks (OCR run metadata).

### Page Structure & Components
1) **Revision List**
- Timeline list: timestamp, actor, sumber (ocr_accept/manual_edit/restore), ringkasan (mis. "Qty 3.5 → 3.500").

2) **Revision Detail (Diff Viewer)**
- Tampilkan before vs after per-field.
- Untuk teks panjang (spesifikasi): diff side-by-side atau unified.

3) **Context Panel**
- OCR Run: engine_name, version, processed_at, input_file_path.
- Link kembali ke item di Tampilan Data.

### Interaction States
- Tombol "Restore" (jika diaktifkan) meminta konfirmasi + alasan; membuat revisi baru dengan change_source=restore.
