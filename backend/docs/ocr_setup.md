# Setup Tesseract OCR (MTO)

Dokumen ini menjelaskan instalasi dan konfigurasi Tesseract OCR untuk fitur OCR MTO di PGN DataLens.

## Windows (UB Mannheim)

### 1) Install Tesseract

Opsi A (disarankan, otomatis via winget):

```powershell
winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
```

Opsi B (manual):
- Unduh installer UB Mannheim: https://github.com/UB-Mannheim/tesseract/wiki

### 2) Verifikasi tesseract.exe

Biasanya terpasang di:
- `C:\Program Files\Tesseract-OCR\tesseract.exe`

Verifikasi dengan menjalankan:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

Untuk memastikan PATH sudah benar (Command Prompt / PowerShell):

```powershell
where tesseract
```

Catatan: Jika `tesseract --version` masih "not recognized", itu berarti PATH belum terbaca (umumnya perlu membuka terminal/IDE baru), namun backend tetap bisa berjalan dengan `TESSERACT_CMD`.

### 3) Set environment variable `TESSERACT_CMD`

Backend akan memakai env var ini untuk menunjuk executable Tesseract tanpa bergantung PATH.

```powershell
setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Tutup dan buka kembali terminal/IDE setelah menjalankan `setx`.

### 4) (Opsional) Bahasa Indonesia `ind`

Di Windows, paket bahasa tidak selalu ikut ter-install. Anda bisa menambahkan `ind.traineddata` ke folder tessdata.

Contoh setup tessdata di user profile:

```powershell
mkdir "$env:USERPROFILE\tesseract\tessdata" -Force
Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ind.traineddata" -OutFile "$env:USERPROFILE\tesseract\tessdata\ind.traineddata"
setx TESSDATA_PREFIX "$env:USERPROFILE\tesseract"
```

Verifikasi bahasa:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

### 5) Verifikasi dari sisi aplikasi (Python)

Fitur OCR memakai helper internal yang otomatis membaca `TESSERACT_CMD`.

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
py -3.12 -c "from backend.services.extraction import _try_import_pytesseract,_ensure_tesseract_ready; p=_try_import_pytesseract(); _ensure_tesseract_ready(p); print(p.get_tesseract_version())"
```

## macOS

```bash
brew install tesseract
tesseract --version
```

## Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y tesseract-ocr
sudo apt install -y tesseract-ocr-ind
tesseract --version
```

## Troubleshooting

### Error: "OCR belum tersedia di server"

Penyebab umum:
- Tesseract belum ter-install
- `TESSERACT_CMD` belum diset / salah path
- Terminal/IDE belum direstart setelah set environment variable

Solusi cepat:
- Pastikan `TESSERACT_CMD` mengarah ke `tesseract.exe` yang valid
- Restart backend FastAPI

### Fallback: Konversi gambar ke PDF

Jika OCR belum tersedia, Anda bisa konversi dokumen gambar ke PDF via endpoint:
- `POST /api/documents/{document_id}/convert-to-pdf`
