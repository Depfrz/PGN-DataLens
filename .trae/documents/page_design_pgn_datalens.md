# Page Design Spec — PGN DataLens (Desktop-first)

## Global

**Layout**: Desktop utama container 1200px, grid 12 kolom; sidebar opsional (min 240px). Mobile: stack vertikal, tabel menjadi kartu.

**Tech note**: Frontend berupa halaman HTML + Tailwind, dengan interaksi via Vanilla JS (atau Alpine.js opsional). Semua operasi data (auth, upload, ekstraksi) memanggil API FastAPI.

**Meta**

* Title template: "PGN DataLens — {Page}"

* Description: "Upload PDF, ekstraksi data (PDF text + OCR fallback), dan kelola proyek/material/dokumen."

* Open Graph: og:title mengikuti title, og:description mengikuti description.

**Global Styles / Tokens**

* Background: #0B1220 (dark) / alternatif light #F6F7FB

* Surface: #111B2E, Border: rgba(255,255,255,0.08)

* Primary: #2F80ED; Success: #27AE60; Danger: #EB5757; Warning: #F2C94C

* Typography: 14/16 body, 18/20 section, 24/28 page title

* Button: primary solid; hover +8% brightness; disabled 40% opacity

* Links: underline on hover; focus ring 2px primary

* Feedback: toast kanan-atas untuk sukses/gagal; inline error di field form

***

## 1) Halaman Login/Daftar

**Layout**: Centered card (max 420px) di tengah layar.

**Meta**

* Title: "PGN DataLens — Login"

**Page Structure**: Logo + judul, form, bantuan.

**Sections & Components**

* Auth Card: tab "Login" / "Daftar".

* Fields: email, password; tombol submit.

* States: loading, error message inline.

* Behavior:

  * Submit memanggil `POST /api/auth/sign-in` atau `POST /api/auth/sign-up`.

  * Sukses: simpan token (mis. HttpOnly cookie atau storage sesuai implementasi) lalu redirect ke Dashboard.

***

## 2) Dashboard

**Layout**: Header topbar + konten utama (grid).

**Meta**

* Title: "PGN DataLens — Dashboard"

**Page Structure**: (A) Topbar, (B) KPI row, (C) Project table.

**Sections & Components**

* Topbar: nama aplikasi, user menu (logout).

* KPI Cards (4): Total Proyek, Total Material, Total Dokumen, Ekstraksi Terakhir (status + timestamp).

* Project Actions: tombol "Proyek Baru" (modal) + search input.

* Project Table: kolom Nama, Update terakhir, Jumlah dokumen, Aksi (Buka, Edit, Hapus).

* Empty state: CTA buat proyek.

**Interaction**

* Load data dari `GET /api/projects` dan agregat KPI dari response atau endpoint ringkasan.

* CRUD proyek via modal:

  * Create: `POST /api/projects`

  * Update: `PATCH /api/projects/{project_id}`

  * Delete: `DELETE /api/projects/{project_id}`

***

## 3) Detail Proyek

**Layout**: Header proyek + tabbed content.

**Meta**

* Title: "PGN DataLens — Detail Proyek"

**Page Structure**: (A) Project header, (B) Tabs: Material | Dokumen, (C) Panel hasil ekstraksi (opsional, di kanan).

**Sections & Components**

* Project Header: breadcrumb (Dashboard > Proyek), nama proyek, tombol edit/hapus.

* Tabs:

  * Tab Material: tabel material + tombol tambah (modal), aksi edit/hapus per baris.

  * Tab Dokumen: daftar dokumen (table) + area upload.

**Upload PDF Module**

* Dropzone + tombol pilih file; validasi tipe PDF; progress bar.

* Behavior:

  * Upload via `POST /api/projects/{project_id}/documents` (multipart).

  * Setelah sukses: item dokumen muncul dengan status `uploaded`.

**Ekstraksi Data Module**

* Tombol "Jalankan Ekstraksi" per dokumen.

* Pipeline UI:

  * Step 1 "Ambil teks PDF".

  * Step 2 "OCR fallback" otomatis bila teks kosong/kurang.

* Output:

  * Panel "Hasil" (JSON viewer + form ringkas untuk koreksi field inti) + tombol simpan.

* Status chip: uploaded / extracting / success / failed, dengan log singkat.

**Responsive**

* Tabs tetap; tabel jadi kartu pada layar kecil.

* Panel hasil ekstraksi berpindah ke bawah konten pada layar kecil.

