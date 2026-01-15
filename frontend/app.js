const API_BASE = ''

const I18N = {
  id: {
    login_title: 'Login',
    login_desc: 'Masuk untuk mengelola proyek, dokumen, dan material.',
    email_label: 'Email',
    password_label: 'Password',
    btn_login: 'Login',
    btn_signup: 'Daftar',
    btn_forgot_password: 'Lupa password?',
    token_note: 'Token disimpan di browser untuk prototipe.',
    resend_ok: '',
    login_ok: 'Login berhasil',
    signup_ok: 'Akun dibuat & login berhasil',
    dup_email_title: 'Email sudah terdaftar',
    dup_email_desc:
      'Silakan login jika Anda sudah punya akun. Jika lupa password, klik "Lupa password?". Atau gunakan email lain.',
    email_check_failed: 'Gagal memeriksa email. Silakan coba lagi.',
    recovery_sent: 'Jika email terdaftar, email pemulihan password sudah dikirim.',
    email_required: 'Email wajib diisi',
    password_required: 'Password wajib diisi',
    lang_label: 'Bahasa',
  },
  en: {
    login_title: 'Sign in',
    login_desc: 'Sign in to manage projects, documents, and materials.',
    email_label: 'Email',
    password_label: 'Password',
    btn_login: 'Sign in',
    btn_signup: 'Sign up',
    btn_forgot_password: 'Forgot password?',
    token_note: 'Token is stored in the browser for prototyping.',
    resend_ok: '',
    login_ok: 'Signed in successfully',
    signup_ok: 'Account created & signed in',
    dup_email_title: 'Email already registered',
    dup_email_desc:
      'Please sign in if you already have an account. If you forgot your password, click "Forgot password?". Or try a different email address.',
    email_check_failed: 'Could not check email. Please try again.',
    recovery_sent: 'If the email exists, a password recovery email has been sent.',
    email_required: 'Email is required',
    password_required: 'Password is required',
    lang_label: 'Language',
  },
}

function getLang() {
  return localStorage.getItem('pgn_lang') || 'id'
}

function setLang(lang) {
  localStorage.setItem('pgn_lang', lang)
}

function t(key) {
  const lang = getLang()
  return (I18N[lang] && I18N[lang][key]) || I18N.id[key] || key
}

function qs(sel, el = document) {
  return el.querySelector(sel)
}

function qsa(sel, el = document) {
  return Array.from(el.querySelectorAll(sel))
}

function getToken() {
  return localStorage.getItem('pgn_token') || ''
}

function setToken(token) {
  localStorage.setItem('pgn_token', token)
}

function clearToken() {
  localStorage.removeItem('pgn_token')
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {})
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, Object.assign({}, opts, { headers }))
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }
  if (!res.ok) {
    const detail = json && json.detail
    let msg = `HTTP ${res.status}`
    let code = null
    if (typeof detail === 'string') {
      msg = detail
    } else if (detail && typeof detail === 'object') {
      msg = detail.message || msg
      code = detail.code || null
    }
    if (res.status === 404 && msg === 'Not Found' && String(path || '').startsWith('/api/')) {
      msg =
        'API tidak ditemukan (404). Pastikan backend FastAPI sudah direstart dan UI dibuka dari backend (mis. http://localhost:8000/), bukan dari Live Server.'
    }
    const err = new Error(msg)
    err.code = code
    err.status = res.status
    throw err
  }
  return json
}

function toast(message, type = 'info') {
  const el = document.createElement('div')
  el.className = `fixed top-4 right-4 z-50 max-w-sm rounded-xl border px-4 py-3 shadow-lg ${
    type === 'error'
      ? 'border-red-500/30 bg-red-950/60 text-red-100'
      : type === 'success'
        ? 'border-emerald-500/30 bg-emerald-950/60 text-emerald-100'
        : 'border-slate-700/60 bg-slate-900/80 text-slate-100'
  }`
  el.textContent = message
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 2600)
}

function isImageFile(f) {
  if (!f) return false
  const t = (f.type || '').toLowerCase()
  if (t === 'image/jpeg' || t === 'image/png' || t === 'image/webp') return true
  const name = (f.name || '').toLowerCase()
  return (
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg') ||
    name.endsWith('.png') ||
    name.endsWith('.webp')
  )
}

function isPdfFile(f) {
  if (!f) return false
  const t = (f.type || '').toLowerCase()
  if (t === 'application/pdf') return true
  const name = (f.name || '').toLowerCase()
  return name.endsWith('.pdf')
}

async function getImageResolution(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve({ width: img.naturalWidth || 0, height: img.naturalHeight || 0 })
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Gagal membaca resolusi gambar'))
    }
    img.src = url
  })
}

function formatBytes(n) {
  const b = Number(n || 0)
  if (!b || b < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(b) / Math.log(1024)))
  const v = b / Math.pow(1024, i)
  const txt = i === 0 ? String(Math.round(v)) : v.toFixed(v >= 10 ? 1 : 2)
  return `${txt} ${units[i]}`
}

function extForMime(mime) {
  const t = String(mime || '').toLowerCase()
  if (t === 'image/png') return '.png'
  if (t === 'image/webp') return '.webp'
  return '.jpg'
}

async function resizeImageFileIfNeeded(file, { maxDim = 2000, maxBytes = 5 * 1024 * 1024 } = {}) {
  const { width, height } = await getImageResolution(file)
  if (!width || !height) throw new Error('Gagal membaca resolusi gambar')
  if (width <= maxDim && height <= maxDim) return { file, resized: false, width, height }

  const scale = Math.min(1, maxDim / width, maxDim / height)
  const targetW = Math.max(1, Math.round(width * scale))
  const targetH = Math.max(1, Math.round(height * scale))

  let source = null
  if (window.createImageBitmap) {
    try {
      source = await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      source = await createImageBitmap(file)
    }
  }

  const canvas = document.createElement('canvas')
  canvas.width = targetW
  canvas.height = targetH
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Browser tidak mendukung Canvas')

  if (source) {
    ctx.drawImage(source, 0, 0, targetW, targetH)
    try {
      source.close && source.close()
    } catch {}
  } else {
    const url = URL.createObjectURL(file)
    try {
      const img = await new Promise((resolve, reject) => {
        const el = new Image()
        el.onload = () => resolve(el)
        el.onerror = () => reject(new Error('Gagal memuat gambar untuk resize'))
        el.src = url
      })
      ctx.drawImage(img, 0, 0, targetW, targetH)
    } finally {
      URL.revokeObjectURL(url)
    }
  }

  const preferred = ['image/jpeg', 'image/png', 'image/webp'].includes(String(file.type || '').toLowerCase())
    ? String(file.type || '').toLowerCase()
    : 'image/jpeg'

  async function canvasToBlob(type, quality) {
    return await new Promise((resolve) => {
      try {
        canvas.toBlob((b) => resolve(b || null), type, quality)
      } catch {
        resolve(null)
      }
    })
  }

  let blob = await canvasToBlob(preferred, preferred === 'image/jpeg' ? 0.9 : 0.92)
  if (!blob) blob = await canvasToBlob('image/jpeg', 0.9)
  if (!blob) throw new Error('Gagal melakukan resize gambar')

  if (blob.size > maxBytes) {
    const qList = [0.85, 0.78, 0.7]
    for (const q of qList) {
      const b = await canvasToBlob('image/jpeg', q)
      if (b && b.size <= maxBytes) {
        blob = b
        break
      }
    }
  }

  if (blob.size > maxBytes) {
    throw new Error('Ukuran file melebihi 5MB setelah resize')
  }

  const base = (file.name || 'upload').replace(/\.[a-z0-9]+$/i, '')
  const newName = `${base}${extForMime(blob.type)}`
  const outFile = new File([blob], newName, { type: blob.type })
  return { file: outFile, resized: true, width: targetW, height: targetH }
}

function uploadWithProgress(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`, true)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.responseType = 'text'

    xhr.upload.onprogress = (ev) => {
      if (!onProgress) return
      if (ev.lengthComputable) onProgress(ev.loaded || 0, ev.total || 0)
      else onProgress(ev.loaded || 0, null)
    }

    xhr.onload = () => {
      const text = xhr.responseText || ''
      let json = null
      try {
        json = text ? JSON.parse(text) : null
      } catch {
        json = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(json)
        return
      }
      const detail = json && json.detail
      let msg = `HTTP ${xhr.status}`
      let code = null
      if (typeof detail === 'string') msg = detail
      else if (detail && typeof detail === 'object') {
        msg = detail.message || msg
        code = detail.code || null
      } else if (text) msg = text
      const err = new Error(msg)
      err.code = code
      err.status = xhr.status
      reject(err)
    }

    xhr.onerror = () => {
      const err = new Error('Upload gagal. Periksa koneksi dan coba lagi.')
      err.status = 0
      reject(err)
    }

    xhr.onabort = () => {
      const err = new Error('Upload dibatalkan')
      err.status = 0
      reject(err)
    }

    xhr.send(formData)
  })
}

function setRoute(hash) {
  window.location.hash = hash
}

function parseRoute() {
  const h = window.location.hash.replace(/^#/, '')
  if (!h || h === '/') return { name: 'dashboard', params: {} }
  if (h === '/login') return { name: 'login', params: {} }
  const m = h.match(/^\/projects\/([^/]+)$/)
  if (m) return { name: 'project', params: { projectId: m[1] } }
  return { name: 'dashboard', params: {} }
}

function layout(content) {
  return `
    <div class="mx-auto max-w-6xl px-4 py-6">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="h-10 w-10 rounded-xl bg-blue-600/20 ring-1 ring-blue-500/30"></div>
          <div>
            <div class="text-sm text-slate-400">PGN DataLens</div>
            <div class="text-lg font-semibold">Arsip & Data Material</div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-dashboard" class="rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-slate-800/60">Dashboard</button>
          <button id="btn-logout" class="rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-slate-800/60">Logout</button>
        </div>
      </div>
      <div class="mt-6">${content}</div>
    </div>
  `
}

function loginView() {
  return `
    <div class="mx-auto mt-16 max-w-md rounded-2xl border border-slate-800 bg-slate-900/40 p-6 shadow">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xl font-semibold">${t('login_title')}</div>
          <div class="mt-1 text-sm text-slate-400">${t('login_desc')}</div>
        </div>
        <div class="shrink-0">
          <label class="text-[11px] text-slate-400">${t('lang_label')}</label>
          <select id="lang" class="mt-1 w-28 rounded-lg border border-slate-800 bg-slate-950/60 px-2 py-2 text-xs outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="id">ID</option>
            <option value="en">EN</option>
          </select>
        </div>
      </div>
      <div class="mt-6 grid gap-3">
        <div>
          <label class="text-xs text-slate-400">${t('email_label')}</label>
          <input id="email" type="email" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
        </div>
        <div>
          <label class="text-xs text-slate-400">${t('password_label')}</label>
          <input id="password" type="password" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
        </div>
        <div class="grid grid-cols-2 gap-2 pt-2">
          <button id="btn-signin" class="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium hover:bg-blue-500">${t('btn_login')}</button>
          <button id="btn-signup" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium hover:bg-slate-800">${t('btn_signup')}</button>
        </div>
        <button id="btn-forgot" class="text-left text-xs text-slate-400 hover:text-slate-200">${t('btn_forgot_password')}</button>
      </div>
      <div class="mt-4 text-xs text-slate-500">${t('token_note')}</div>
    </div>
  `
}

function dashboardView(state) {
  const rows = state.projects
    .map(
      (p) => `
      <tr class="border-t border-slate-800/60">
        <td class="py-3 pr-3">
          <div class="font-medium text-slate-100">${escapeHtml(p.name)}</div>
          <div class="text-xs text-slate-400">${escapeHtml(p.location || '-')}${p.year ? ` • ${p.year}` : ''}</div>
        </td>
        <td class="py-3 pr-3 text-sm text-slate-300">${escapeHtml(p.status || '-')}</td>
        <td class="py-3 pr-3 text-sm text-slate-300">${p.total_documents}</td>
        <td class="py-3 pr-3 text-sm text-slate-300">${p.total_material_rows}</td>
        <td class="py-3 pr-3 text-sm text-slate-300">${(p.total_pipe_length_m || 0).toFixed(2)}</td>
        <td class="py-3 text-right">
          <button data-open="${p.id}" class="rounded-lg bg-slate-800/60 px-3 py-2 text-xs hover:bg-slate-700">Buka</button>
        </td>
      </tr>
    `
    )
    .join('')

  return layout(`
    <div class="grid gap-4 md:grid-cols-4">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <div class="text-xs text-slate-400">Total Proyek</div>
        <div class="mt-2 text-2xl font-semibold">${state.projects.length}</div>
      </div>
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <div class="text-xs text-slate-400">Total Dokumen</div>
        <div class="mt-2 text-2xl font-semibold">${state.kpi.totalDocs}</div>
      </div>
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <div class="text-xs text-slate-400">Total Material (rows)</div>
        <div class="mt-2 text-2xl font-semibold">${state.kpi.totalMaterials}</div>
      </div>
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <div class="text-xs text-slate-400">Total Panjang Pipa (m)</div>
        <div class="mt-2 text-2xl font-semibold">${state.kpi.totalPipe.toFixed(2)}</div>
      </div>
    </div>

    <div class="mt-6 grid gap-4 md:grid-cols-3">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 md:col-span-1">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold">Proyek Baru</div>
            <div class="text-xs text-slate-400">Buat header proyek untuk pengarsipan.</div>
          </div>
        </div>
        <div class="mt-4 grid gap-3">
          <div>
            <label class="text-xs text-slate-400">Nama</label>
            <input id="p-name" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
          <div>
            <label class="text-xs text-slate-400">Lokasi/Area</label>
            <input id="p-location" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-xs text-slate-400">Tahun</label>
              <input id="p-year" type="number" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
            <div>
              <label class="text-xs text-slate-400">Status</label>
              <select id="p-status" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40">
                <option value="">-</option>
                <option value="Konstruksi">Konstruksi</option>
                <option value="Commissioning">Commissioning</option>
                <option value="Gas In">Gas In</option>
              </select>
            </div>
          </div>
          <button id="btn-create-project" class="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium hover:bg-blue-500">Simpan Proyek</button>
        </div>
      </div>

      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 md:col-span-2">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold">Daftar Proyek</div>
            <div class="text-xs text-slate-400">Klik "Buka" untuk melihat dokumen dan material.</div>
          </div>
        </div>

        <div class="mt-4 overflow-hidden rounded-xl border border-slate-800">
          <table class="w-full">
            <thead class="bg-slate-900">
              <tr class="text-left text-xs text-slate-400">
                <th class="px-3 py-3">Proyek</th>
                <th class="px-3 py-3">Status</th>
                <th class="px-3 py-3">Dokumen</th>
                <th class="px-3 py-3">Material</th>
                <th class="px-3 py-3">Pipa (m)</th>
                <th class="px-3 py-3"></th>
              </tr>
            </thead>
            <tbody class="bg-slate-950/30">${rows || ''}</tbody>
          </table>
        </div>
      </div>
    </div>
  `)
}

function projectView(state) {
  const p = state.project
  const docsRows = state.documents
    .map(
      (d) => `
      <div class="rounded-xl border border-slate-800 bg-slate-950/30 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-medium">${escapeHtml(d.filename)}</div>
            <div class="mt-1 text-xs text-slate-400">${escapeHtml(d.document_type)}${d.document_number ? ` • ${escapeHtml(d.document_number)}` : ''}</div>
          </div>
          <div class="flex items-center gap-2">
            ${d.download_url ? `<a class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800" target="_blank" href="${d.download_url}">View</a>` : ''}
            ${d.file_kind !== 'image' ? `<button data-extract="${d.id}" class="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium hover:bg-blue-500">Ekstrak</button>` : ''}
            <button data-mto-import="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">OCR MTO</button>
            <button data-mto-csv="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">MTO CSV</button>
            ${d.file_kind === 'image' ? `<button data-img2pdf="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">Konversi PDF</button>` : ''}
            <button data-del-doc="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">Hapus</button>
          </div>
        </div>
        ${d.file_kind === 'image' && d.download_url ? `<div class="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40"><img alt="${escapeHtml(d.filename)}" src="${d.download_url}" class="max-h-64 w-full object-contain" /></div>` : ''}
        <div data-doc-out="${d.id}" class="mt-3 hidden rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-200"></div>
        <div class="mt-3 flex items-center justify-between">
          <div class="text-xs text-slate-400">Status: <span class="text-slate-200">${escapeHtml(d.status)}</span></div>
        </div>
      </div>
    `
    )
    .join('')

  return layout(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-sm text-slate-400">Detail Proyek</div>
          <div class="mt-1 text-xl font-semibold">${escapeHtml(p.name)}</div>
          <div class="mt-1 text-sm text-slate-400">${escapeHtml(p.location || '-')}${p.year ? ` • ${p.year}` : ''}${p.status ? ` • ${escapeHtml(p.status)}` : ''}</div>
        </div>
        <button id="btn-back" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Kembali</button>
      </div>
    </div>

    <div class="mt-6 grid gap-4 md:grid-cols-3">
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 md:col-span-1">
        <div class="text-sm font-semibold">Upload Dokumen</div>
        <div class="mt-1 text-xs text-slate-400">PDF untuk ekstraksi, atau gambar (JPEG/PNG/WEBP) untuk preview.</div>
        <div class="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/30 p-4">
          <input id="file" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" class="block w-full text-sm" />
          <div class="mt-2 text-[11px] text-slate-500">Maks ${escapeHtml(formatBytes(5 * 1024 * 1024))}. Format gambar: JPEG, PNG, WEBP. Gambar di atas 2000×2000 akan di-resize otomatis.</div>
          <div id="img-preview" class="mt-3 hidden overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40"></div>
          <button id="btn-upload" class="mt-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium hover:bg-blue-500">Upload</button>
          <button id="btn-upload-retry" class="mt-2 hidden w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Coba lagi</button>
          <div id="upload-progress-wrap" class="mt-3 hidden">
            <div class="h-2 w-full overflow-hidden rounded bg-slate-800">
              <div id="upload-progress-bar" class="h-2 w-0 bg-blue-500"></div>
            </div>
            <div id="upload-progress-text" class="mt-1 text-[11px] text-slate-400"></div>
          </div>
          <div id="upload-status" class="mt-3 text-xs text-slate-400"></div>
        </div>
      </div>
      <div class="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 md:col-span-2">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold">Dokumen</div>
            <div class="text-xs text-slate-400">Upload, ekstrak, dan simpan hasil.</div>
          </div>
        </div>
        <div class="mt-4 grid gap-3">${docsRows || '<div class="text-sm text-slate-400">Belum ada dokumen.</div>'}</div>
      </div>
    </div>

    <div class="mt-6 rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-sm font-semibold">Material</div>
          <div class="text-xs text-slate-400">Hasil ekstraksi akan masuk ke tabel ini.</div>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-2">
          <select id="mat-doc" class="w-56 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="">Semua dokumen</option>
            ${(state.documents || [])
              .map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.filename)}</option>`)
              .join('')}
          </select>
          <input id="mat-q" placeholder="Cari..." class="w-44 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <input id="mat-size" placeholder="Size" class="w-28 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <input id="mat-unit" placeholder="Unit" class="w-24 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <select id="mat-limit" class="w-24 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="50">50</option>
            <option value="200" selected>200</option>
            <option value="500">500</option>
          </select>
          <button id="btn-search" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Terapkan</button>
          <button id="btn-mat-delete-all" class="rounded-lg border border-rose-700/60 bg-rose-950/30 px-3 py-2 text-sm text-rose-100 hover:bg-rose-900/30" disabled>Hapus Semua</button>
        </div>
      </div>
      <div class="mt-4 overflow-hidden rounded-xl border border-slate-800">
        <table class="w-full">
          <thead id="mat-thead" class="bg-slate-900">
            <tr class="text-left text-xs text-slate-400">
              <th class="px-3 py-3"><button data-sort="description" class="hover:text-slate-200">Nama Item</button></th>
              <th class="px-3 py-3">Spesifikasi</th>
              <th class="px-3 py-3"><button data-sort="size" class="hover:text-slate-200">Size</button></th>
              <th class="px-3 py-3"><button data-sort="quantity" class="hover:text-slate-200">Quantity</button></th>
              <th class="px-3 py-3"><button data-sort="unit" class="hover:text-slate-200">Unit</button></th>
              <th class="px-3 py-3"></th>
            </tr>
          </thead>
          <tbody id="mat-tbody" class="bg-slate-950/30"></tbody>
        </table>
      </div>
      <div class="mt-3 flex items-center justify-between">
        <div id="mat-status" class="text-xs text-slate-400"></div>
        <button id="mat-load-more" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800" disabled>Muat lagi</button>
      </div>
    </div>
  `)
}

function materialRowsHtml(materials) {
  function badge(text, cls) {
    return `<span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] ${cls}">${escapeHtml(text)}</span>`
  }
  return (materials || [])
    .map(
      (m) => `
      <tr class="border-t border-slate-800/60 ${m.data_source === 'ocr' ? 'bg-amber-950/20' : ''}">
        <td class="px-3 py-3 align-top">
          <div class="flex items-start gap-2">
            <div class="text-sm font-medium">${escapeHtml(m.description)}</div>
            <div class="mt-0.5 flex flex-wrap gap-1">
              ${m.data_source === 'ocr' ? badge('OCR', 'border-amber-500/30 bg-amber-950/40 text-amber-100') : ''}
              ${m.needs_review ? badge('Perlu Review', 'border-rose-500/30 bg-rose-950/40 text-rose-100') : ''}
              ${m.verification_status === 'approved' ? badge('Terverifikasi', 'border-emerald-500/30 bg-emerald-950/40 text-emerald-100') : ''}
              ${m.verification_status === 'rejected' ? badge('Ditolak', 'border-slate-600/60 bg-slate-900/60 text-slate-200') : ''}
            </div>
          </div>
        </td>
        <td class="px-3 py-3 align-top">${specBulletsHtml(m.spec)}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${escapeHtml(m.size || '-')}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${m.quantity == null ? '-' : m.quantity}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${escapeHtml(m.unit || '-')}</td>
        <td class="px-3 py-3 text-right">
          <div class="flex items-center justify-end gap-2">
            ${m.data_source === 'ocr' || m.needs_review ? `<button data-review-mat="${m.id}" class="rounded-lg border border-amber-600/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-100 hover:bg-amber-900/30">Review</button>` : ''}
            <button data-del-mat="${m.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">Hapus</button>
          </div>
        </td>
      </tr>
    `
    )
    .join('')
}

function specBulletsHtml(spec) {
  const raw = (spec || '').trim()
  if (!raw) return '<div class="text-xs text-slate-500">-</div>'
  const parts = raw
    .split(/\s*[\n,]\s*/)
    .map((s) => s.trim())
    .filter(Boolean)
  const items = parts
    .slice(0, 12)
    .map((p) => `<li class="leading-5">${escapeHtml(p)}</li>`)
    .join('')
  const more = parts.length > 12 ? `<li class="text-slate-500">+${parts.length - 12} lainnya</li>` : ''
  return `<ul class="list-disc pl-4 text-xs text-slate-400">${items}${more}</ul>`
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

async function render() {
  const appEl = qs('#app')
  const route = parseRoute()

  if (!getToken() && route.name !== 'login') {
    setRoute('/login')
    return
  }

  if (route.name === 'login') {
    appEl.innerHTML = loginView()

    const langSel = qs('#lang')
    if (langSel) {
      langSel.value = getLang()
      langSel.addEventListener('change', () => {
        setLang(langSel.value)
        render()
      })
    }

    qs('#btn-forgot').addEventListener('click', async () => {
      const email = qs('#email').value.trim()
      if (!email) {
        toast(t('email_required'), 'error')
        return
      }
      try {
        await api('/api/auth/password-recovery', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email })
        })
        toast(t('recovery_sent'), 'success')
      } catch (e) {
        toast(e.message, 'error')
      }
    })

    qs('#btn-signin').addEventListener('click', async () => {
      const email = qs('#email').value.trim()
      const password = qs('#password').value
      try {
        const s = await api('/api/auth/sign-in', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        })
        setToken(s.access_token)
        toast(t('login_ok'), 'success')
        setRoute('/')
      } catch (e) {
        toast(e.message, 'error')
      }
    })
    qs('#btn-signup').addEventListener('click', async () => {
      const email = qs('#email').value.trim()
      const password = qs('#password').value
      try {
        if (!email) {
          toast(t('email_required'), 'error')
          return
        }
        if (!password) {
          toast(t('password_required'), 'error')
          return
        }

        try {
          const chk = await api(`/api/auth/email-availability?email=${encodeURIComponent(email)}`)
          if (chk && chk.available === false) {
            toast(`${t('dup_email_title')}. ${t('dup_email_desc')}`, 'error')
            return
          }
        } catch {
          toast(t('email_check_failed'), 'error')
          return
        }

        const s = await api('/api/auth/sign-up', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        })
        if (!s.access_token) {
          toast('Akun dibuat, tetapi token tidak tersedia. Silakan login.', 'error')
          return
        }

        setToken(s.access_token)
        toast(t('signup_ok'), 'success')
        setRoute('/')
      } catch (e) {
        if (e.status === 409 || e.code === 'duplicate_email') {
          toast(`${t('dup_email_title')}. ${t('dup_email_desc')}`, 'error')
          return
        }
        toast(e.message, 'error')
      }
    })
    return
  }


  if (route.name === 'dashboard') {
    try {
      const projects = await api('/api/projects')
      const kpi = {
        totalDocs: projects.reduce((a, p) => a + (p.total_documents || 0), 0),
        totalMaterials: projects.reduce((a, p) => a + (p.total_material_rows || 0), 0),
        totalPipe: projects.reduce((a, p) => a + (p.total_pipe_length_m || 0), 0),
      }
      appEl.innerHTML = dashboardView({ projects, kpi })
      wireTopbar()
      qs('#btn-create-project').addEventListener('click', async () => {
        const name = qs('#p-name').value.trim()
        const location = qs('#p-location').value.trim()
        const year = qs('#p-year').value ? Number(qs('#p-year').value) : null
        const status = qs('#p-status').value || null
        if (!name) {
          toast('Nama proyek wajib diisi', 'error')
          return
        }
        try {
          await api('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, location: location || null, year, status })
          })
          toast('Proyek dibuat', 'success')
          render()
        } catch (e) {
          toast(e.message, 'error')
        }
      })
      qsa('[data-open]').forEach((btn) => {
        btn.addEventListener('click', () => {
          setRoute(`/projects/${btn.getAttribute('data-open')}`)
        })
      })
    } catch (e) {
      toast(e.message, 'error')
      clearToken()
      setRoute('/login')
    }
    return
  }

  if (route.name === 'project') {
    const projectId = route.params.projectId
    try {
      const project = await api(`/api/projects/${projectId}`)
      const documents = await api(`/api/projects/${projectId}/documents`)
      appEl.innerHTML = projectView({ project, documents, materials: [] })
      wireTopbar()
      qs('#btn-back').addEventListener('click', () => setRoute('/'))

      const matState = {
        q: '',
        size: '',
        unit: '',
        documentId: '',
        sortBy: 'created_at',
        sortDir: 'desc',
        limit: 200,
        offset: 0,
        nextOffset: null
      }

      function modal(html) {
        const wrap = document.createElement('div')
        wrap.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4'
        wrap.innerHTML = `<div class="w-full max-w-4xl rounded-2xl border border-slate-800 bg-slate-950 shadow-xl">${html}</div>`
        document.body.appendChild(wrap)
        function close() {
          wrap.remove()
        }
        wrap.addEventListener('click', (ev) => {
          if (ev.target === wrap) close()
          const btn = ev.target.closest('[data-close]')
          if (btn) close()
        })
        return { el: wrap, close }
      }

      async function openReview(materialId) {
        const ctx = await api(`/api/materials/${materialId}/ocr-context`)
        const hist = await api(`/api/materials/${materialId}/history`)
        const mat = (ctx && ctx.material) || {}
        const run = (ctx && ctx.ocr_run) || null
        const ext = (ctx && ctx.ocr_extraction) || null
        const doc = (documents || []).find((d) => d.id === mat.document_id) || null
        const ocr = (ext && ext.normalized_fields) || {}
        const flags = (ext && ext.flags && ext.flags.flags) || []

        const m = modal(`
          <div class="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <div>
              <div class="text-sm text-slate-400">Review OCR</div>
              <div class="mt-1 text-lg font-semibold">${escapeHtml(mat.description || '-')}</div>
            </div>
            <button data-close class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Tutup</button>
          </div>
          <div class="grid gap-4 p-5 md:grid-cols-2">
            <div class="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div class="text-sm font-semibold">Nilai saat ini</div>
              <div class="mt-3 grid gap-3">
                <div>
                  <label class="text-xs text-slate-400">Nama Item</label>
                  <input id="rv-desc" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm" value="${escapeHtml(mat.description || '')}" />
                </div>
                <div>
                  <label class="text-xs text-slate-400">Spesifikasi</label>
                  <textarea id="rv-spec" rows="5" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">${escapeHtml(mat.spec || '')}</textarea>
                </div>
                <div class="grid grid-cols-3 gap-3">
                  <div>
                    <label class="text-xs text-slate-400">Size</label>
                    <input id="rv-size" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm" value="${escapeHtml(mat.size || '')}" />
                  </div>
                  <div>
                    <label class="text-xs text-slate-400">Quantity</label>
                    <input id="rv-qty" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm" value="${mat.quantity == null ? '' : escapeHtml(mat.quantity)}" />
                  </div>
                  <div>
                    <label class="text-xs text-slate-400">Unit</label>
                    <input id="rv-unit" class="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm" value="${escapeHtml(mat.unit || '')}" />
                  </div>
                </div>
                <div class="text-xs text-slate-500">Status: ${escapeHtml(mat.verification_status || 'draft')}</div>
              </div>
            </div>

            <div class="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div class="flex items-center justify-between">
                <div class="text-sm font-semibold">Nilai OCR</div>
                ${doc && doc.download_url ? `<a class="text-xs text-slate-300 underline hover:text-white" target="_blank" href="${doc.download_url}">Buka dokumen</a>` : ''}
              </div>
              <div class="mt-3 grid gap-2 text-sm">
                <div class="flex items-center justify-between gap-3"><div class="text-slate-400">Nama Item</div><div class="text-right">${escapeHtml((ocr && ocr.description) || '-')}</div></div>
                <div class="flex items-start justify-between gap-3"><div class="text-slate-400">Spesifikasi</div><div class="max-w-[60%] text-right text-xs text-slate-200">${specBulletsHtml((ocr && ocr.spec) || '')}</div></div>
                <div class="flex items-center justify-between gap-3"><div class="text-slate-400">Size</div><div class="text-right">${escapeHtml((ocr && ocr.size) || '-')}</div></div>
                <div class="flex items-center justify-between gap-3"><div class="text-slate-400">Quantity</div><div class="text-right">${(ocr && ocr.quantity) == null ? '-' : escapeHtml(ocr.quantity)}</div></div>
                <div class="flex items-center justify-between gap-3"><div class="text-slate-400">Unit</div><div class="text-right">${escapeHtml((ocr && ocr.unit) || '-')}</div></div>
              </div>
              <div class="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <div class="text-xs font-semibold text-slate-300">Metadata</div>
                <div class="mt-2 text-xs text-slate-400">
                  <div>OCR run: ${run ? escapeHtml(run.id) : '-'}</div>
                  <div>Engine: ${run ? escapeHtml(run.engine_name || '-') : '-'} ${run ? escapeHtml(run.engine_version || '') : ''}</div>
                  <div>Waktu: ${run ? escapeHtml(run.processed_at || '-') : '-'}</div>
                  ${flags && flags.length ? `<div class="mt-2 text-rose-200">Flag: ${escapeHtml(flags.join(', '))}</div>` : '<div class="mt-2 text-slate-500">Tidak ada flag</div>'}
                </div>
              </div>

              <div class="mt-4">
                <div class="text-xs font-semibold text-slate-300">Histori</div>
                <div class="mt-2 max-h-40 overflow-auto rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs text-slate-300">
                  ${(hist || [])
                    .slice(0, 15)
                    .map((h) => `<div class="border-b border-slate-800/60 py-2"><div class="text-slate-400">${escapeHtml(h.changed_at || '')} • ${escapeHtml(h.change_source || '')}</div><div class="mt-1 text-slate-200">${escapeHtml(JSON.stringify(h.after || {}))}</div></div>`)
                    .join('') || '<div class="text-slate-500">Belum ada histori.</div>'}
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-center justify-between border-t border-slate-800 px-5 py-4">
            <div class="text-xs text-slate-500">Approve akan menandai item sebagai terverifikasi.</div>
            <div class="flex items-center gap-2">
              <button id="rv-reject" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Tolak</button>
              <button id="rv-approve" class="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium hover:bg-emerald-500">Approve</button>
            </div>
          </div>
        `)

        const approveBtn = qs('#rv-approve', m.el)
        const rejectBtn = qs('#rv-reject', m.el)

        async function submit(decision) {
          const patch = {
            description: qs('#rv-desc', m.el).value.trim(),
            spec: qs('#rv-spec', m.el).value,
            size: qs('#rv-size', m.el).value.trim() || null,
            quantity: qs('#rv-qty', m.el).value.trim() ? Number(qs('#rv-qty', m.el).value.trim()) : null,
            unit: qs('#rv-unit', m.el).value.trim() || null,
          }
          try {
            await api(`/api/materials/${materialId}/review`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ decision, patch }),
            })
            toast(decision === 'approved' ? 'Item disetujui' : 'Item ditolak', 'success')
            m.close()
            await loadMaterials(true)
          } catch (e) {
            toast(e.message, 'error')
          }
        }

        approveBtn.addEventListener('click', () => submit('approved'))
        rejectBtn.addEventListener('click', () => submit('rejected'))
      }

      async function loadMaterials(reset = false) {
        const statusEl = qs('#mat-status')
        const tbody = qs('#mat-tbody')
        const btnMore = qs('#mat-load-more')
        try {
          btnMore.disabled = true
          statusEl.textContent = 'Memuat material...'
          if (reset) {
            matState.offset = 0
            matState.nextOffset = null
            tbody.innerHTML = ''
          }

          const url = `/api/projects/${projectId}/materials/page?` +
            `document_id=${encodeURIComponent(matState.documentId)}&` +
            `q=${encodeURIComponent(matState.q)}&` +
            `size=${encodeURIComponent(matState.size)}&` +
            `unit=${encodeURIComponent(matState.unit)}&` +
            `sort_by=${encodeURIComponent(matState.sortBy)}&` +
            `sort_dir=${encodeURIComponent(matState.sortDir)}&` +
            `limit=${encodeURIComponent(matState.limit)}&` +
            `offset=${encodeURIComponent(matState.offset)}`

          const res = await api(url)
          const items = res.items || []
          const html = materialRowsHtml(items)
          if (matState.offset === 0) tbody.innerHTML = html
          else tbody.insertAdjacentHTML('beforeend', html)
          matState.nextOffset = res.next_offset
          statusEl.textContent = `${(tbody.querySelectorAll('tr') || []).length} baris ditampilkan`
          btnMore.disabled = !matState.nextOffset
        } catch (e) {
          qs('#mat-status').textContent = ''
          toast(e.message, 'error')
        }
      }

      qs('#mat-load-more').addEventListener('click', async () => {
        if (!matState.nextOffset) return
        matState.offset = matState.nextOffset
        await loadMaterials(false)
      })

      qs('#btn-search').addEventListener('click', async () => {
        matState.documentId = qs('#mat-doc').value || ''
        matState.q = qs('#mat-q').value.trim()
        matState.size = qs('#mat-size').value.trim()
        matState.unit = qs('#mat-unit').value.trim()
        matState.limit = parseInt(qs('#mat-limit').value, 10) || 200
        await loadMaterials(true)
      })

      const deleteAllBtn = qs('#btn-mat-delete-all')
      const matDocSel = qs('#mat-doc')
      function syncDeleteAllEnabled() {
        if (!deleteAllBtn || !matDocSel) return
        deleteAllBtn.disabled = !(matDocSel.value || '').trim()
      }
      syncDeleteAllEnabled()
      matDocSel?.addEventListener('change', syncDeleteAllEnabled)

      deleteAllBtn?.addEventListener('click', async () => {
        const docId = (matDocSel?.value || '').trim()
        if (!docId) {
          toast('Pilih dokumen dulu sebelum Hapus Semua', 'error')
          return
        }
        const ok = window.confirm('Hapus semua material untuk dokumen ini? Tindakan ini tidak dapat dibatalkan.')
        if (!ok) return
        try {
          deleteAllBtn.disabled = true
          await api(`/api/documents/${docId}/materials`, { method: 'DELETE' })
          toast('Semua material untuk dokumen dihapus', 'success')
          await loadMaterials(true)
        } catch (e) {
          toast(e.message, 'error')
        } finally {
          syncDeleteAllEnabled()
        }
      })

      ;['#mat-q', '#mat-size', '#mat-unit'].forEach((sel) => {
        const el = qs(sel)
        el.addEventListener('keydown', async (ev) => {
          if (ev.key === 'Enter') {
            qs('#btn-search').click()
          }
        })
      })

      qs('#mat-thead').addEventListener('click', async (ev) => {
        const btn = ev.target.closest('[data-sort]')
        if (!btn) return
        const key = btn.getAttribute('data-sort')
        if (!key) return
        if (matState.sortBy === key) matState.sortDir = matState.sortDir === 'asc' ? 'desc' : 'asc'
        else {
          matState.sortBy = key
          matState.sortDir = key === 'created_at' ? 'desc' : 'asc'
        }
        await loadMaterials(true)
      })

      qs('#mat-tbody').addEventListener('click', async (ev) => {
        const reviewBtn = ev.target.closest('[data-review-mat]')
        if (reviewBtn) {
          const id = reviewBtn.getAttribute('data-review-mat')
          if (id) {
            try {
              await openReview(id)
            } catch (e) {
              toast(e.message, 'error')
            }
          }
          return
        }
        const btn = ev.target.closest('[data-del-mat]')
        if (!btn) return
        const id = btn.getAttribute('data-del-mat')
        if (!id) return
        try {
          await api(`/api/materials/${id}`, { method: 'DELETE' })
          btn.closest('tr')?.remove()
          toast('Material dihapus', 'success')
          qs('#mat-status').textContent = `${(qs('#mat-tbody').querySelectorAll('tr') || []).length} baris ditampilkan`
        } catch (e) {
          toast(e.message, 'error')
        }
      })

      const fileEl = qs('#file')
      const previewEl = qs('#img-preview')
      const uploadBtn = qs('#btn-upload')
      const retryBtn = qs('#btn-upload-retry')
      const statusEl = qs('#upload-status')
      const progressWrap = qs('#upload-progress-wrap')
      const progressBar = qs('#upload-progress-bar')
      const progressText = qs('#upload-progress-text')
      let lastPreparedFile = null
      let uploading = false

      function resetProgress() {
        if (progressWrap) progressWrap.classList.add('hidden')
        if (progressBar) progressBar.style.width = '0%'
        if (progressText) progressText.textContent = ''
      }

      function setUploadingUi(isUploading) {
        uploading = !!isUploading
        if (uploadBtn) uploadBtn.disabled = uploading
        if (fileEl) fileEl.disabled = uploading
      }

      function showRetry(show) {
        if (!retryBtn) return
        if (show) retryBtn.classList.remove('hidden')
        else retryBtn.classList.add('hidden')
      }

      function setStatus(text) {
        if (statusEl) statusEl.textContent = text || ''
      }

      async function doUpload(fileToSend) {
        const form = new FormData()
        form.append('file', fileToSend)
        resetProgress()
        showRetry(false)
        if (progressWrap) progressWrap.classList.remove('hidden')
        setStatus('Mengupload...')

        function onProgress(loaded, total) {
          if (!progressBar || !progressText) return
          if (total && total > 0) {
            const pct = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)))
            progressBar.style.width = `${pct}%`
            progressText.textContent = `${pct}% • ${formatBytes(loaded)} / ${formatBytes(total)}`
          } else {
            progressBar.style.width = '100%'
            progressText.textContent = `${formatBytes(loaded)} terkirim`
          }
        }

        return await uploadWithProgress(`/api/projects/${projectId}/documents`, form, onProgress)
      }

      if (fileEl && previewEl) {
        let previewUrl = null
        fileEl.addEventListener('change', async () => {
          if (previewUrl) {
            try {
              URL.revokeObjectURL(previewUrl)
            } catch {}
            previewUrl = null
          }
          previewEl.classList.add('hidden')
          previewEl.innerHTML = ''
          resetProgress()
          showRetry(false)
          setStatus('')
          lastPreparedFile = null
          const f = fileEl.files && fileEl.files[0]
          if (!f) return
          if (isImageFile(f)) {
            previewUrl = URL.createObjectURL(f)
            previewEl.innerHTML = `<img alt="Preview" src="${previewUrl}" class="max-h-56 w-full object-contain" />`
            previewEl.classList.remove('hidden')
            try {
              const { width, height } = await getImageResolution(f)
              if (width > 2000 || height > 2000) {
                setStatus('Gambar akan di-resize otomatis sebelum upload.')
              }
            } catch {}
            return
          }
          if (!isPdfFile(f)) {
            toast('Format tidak didukung. Gunakan PDF/JPEG/PNG/WEBP', 'error')
          }
          return
        })
      }

      async function handleUpload() {
        const f = fileEl && fileEl.files && fileEl.files[0]
        if (!f) {
          toast('Pilih file dulu', 'error')
          return
        }

        if (!(isPdfFile(f) || isImageFile(f))) {
          toast('Format tidak didukung. Gunakan PDF/JPEG/PNG/WEBP', 'error')
          return
        }

        const max = 5 * 1024 * 1024
        if (isImageFile(f) && f.size > max) {
          toast(`Ukuran file maksimum ${formatBytes(max)}`, 'error')
          return
        }

        if (uploading) return
        setUploadingUi(true)
        showRetry(false)
        resetProgress()

        try {
          let toSend = f
          if (isImageFile(f)) {
            setStatus('Memproses gambar...')
            const prep = await resizeImageFileIfNeeded(f, { maxDim: 2000, maxBytes: max })
            toSend = prep.file
            lastPreparedFile = toSend
            if (prep.resized) {
              setStatus(`Gambar di-resize ke ${prep.width}×${prep.height}. Mengupload...`)
            }
          }

          await doUpload(toSend)
          toast('Upload berhasil', 'success')
          setStatus('')
          resetProgress()
          showRetry(false)
          setUploadingUi(false)
          render()
        } catch (e) {
          setUploadingUi(false)
          setStatus('')
          resetProgress()
          showRetry(!!(isImageFile(f) || isPdfFile(f)))
          toast(e.message || 'Upload gagal', 'error')
        }
      }

      if (uploadBtn) {
        uploadBtn.addEventListener('click', async () => {
          await handleUpload()
        })
      }

      if (retryBtn) {
        retryBtn.addEventListener('click', async () => {
          const f = fileEl && fileEl.files && fileEl.files[0]
          if (!f) {
            toast('Pilih file dulu', 'error')
            return
          }
          if (uploading) return
          try {
            setUploadingUi(true)
            showRetry(false)
            let toSend = f
            if (isImageFile(f)) {
              toSend = lastPreparedFile || f
            }
            await doUpload(toSend)
            toast('Upload berhasil', 'success')
            setUploadingUi(false)
            setStatus('')
            resetProgress()
            render()
          } catch (e) {
            setUploadingUi(false)
            showRetry(true)
            setStatus('')
            resetProgress()
            toast(e.message || 'Upload gagal', 'error')
          }
        })
      }
      qsa('[data-del-doc]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-del-doc')
          try {
            await api(`/api/documents/${id}`, { method: 'DELETE' })
            toast('Dokumen dihapus', 'success')
            render()
          } catch (e) {
            toast(e.message, 'error')
          }
        })
      })
      qsa('[data-extract]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-extract')
          try {
            toast('Ekstraksi dimulai...', 'info')
            await api(`/api/documents/${id}/extract`, { method: 'POST' })
            toast('Ekstraksi selesai', 'success')
            render()
          } catch (e) {
            toast(e.message, 'error')
          }
        })
      })

      qsa('[data-mto-import]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-mto-import')
          if (!id) return
          const out = qs(`[data-doc-out="${id}"]`)
          if (out) {
            out.classList.add('hidden')
            out.textContent = ''
          }
          try {
            toast('Menjalankan OCR MTO dan menyimpan ke Tampilan Data...', 'info')
            const res = await api(`/api/documents/${id}/mto/import`, { method: 'POST' })
            const inserted = (res && res.inserted_materials) || 0
            const flagged = (res && res.flagged) || 0
            const run = (res && res.ocr_run) || null
            if (out) {
              out.innerHTML = `<div class="text-xs text-slate-300">OCR run: <span class="text-slate-100">${escapeHtml((run && run.id) || '-')}</span></div>` +
                `<div class="mt-1 text-xs text-slate-400">Material OCR tersimpan: <span class="text-slate-200">${inserted}</span> • Flag review: <span class="text-slate-200">${flagged}</span></div>` +
                `<div class="mt-2 text-xs text-slate-500">Gunakan filter dokumen pada tabel Material untuk melihat hasilnya.</div>`
              out.classList.remove('hidden')
            }
            qs('#mat-doc').value = id
            qs('#btn-search').click()
            toast(`OCR MTO selesai: ${inserted} baris tersimpan`, 'success')
          } catch (e) {
            toast(e.message, 'error')
          }
        })
      })

      qsa('[data-mto-csv]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-mto-csv')
          if (!id) return
          try {
            toast('Menyiapkan file CSV...', 'info')
            const mto = await api(`/api/documents/${id}/mto`, { method: 'POST' })
            const outputs = (mto && mto.outputs) || {}
            const csvUrl = outputs.csv && outputs.csv.download_url
            if (csvUrl) {
              window.open(csvUrl, '_blank')
              return
            }

            const token = getToken()
            const res = await fetch(`/api/documents/${id}/mto/csv`, {
              method: 'POST',
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            })
            if (!res.ok) {
              const text = await res.text()
              let msg = `HTTP ${res.status}`
              try {
                const j = text ? JSON.parse(text) : null
                if (j && j.detail) msg = typeof j.detail === 'string' ? j.detail : j.detail.message || msg
              } catch {
                msg = text || msg
              }
              throw new Error(msg)
            }
            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = 'materials_take_off.csv'
            document.body.appendChild(a)
            a.click()
            a.remove()
            URL.revokeObjectURL(url)
          } catch (e) {
            toast(e.message, 'error')
          }
        })
      })

      qsa('[data-img2pdf]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-img2pdf')
          if (!id) return
          const out = qs(`[data-doc-out="${id}"]`)
          if (out) {
            out.classList.add('hidden')
            out.textContent = ''
          }
          try {
            toast('Mengonversi gambar ke PDF...', 'info')
            const res = await api(`/api/documents/${id}/convert-to-pdf`, { method: 'POST' })
            const url = res && res.download_url
            if (out) {
              out.innerHTML = `${url ? `<a class="underline" target="_blank" href="${url}">Download PDF hasil konversi</a>` : ''}`
              out.classList.remove('hidden')
            }
            toast('Konversi selesai. PDF baru ditambahkan ke daftar dokumen.', 'success')
            render()
          } catch (e) {
            toast(e.message, 'error')
          }
        })
      })

      await loadMaterials(true)
    } catch (e) {
      toast(e.message, 'error')
      setRoute('/')
    }
    return
  }
}

function wireTopbar() {
  const bd = qs('#btn-dashboard')
  const lo = qs('#btn-logout')
  if (bd) bd.addEventListener('click', () => setRoute('/'))
  if (lo) {
    lo.addEventListener('click', () => {
      clearToken()
      setRoute('/login')
    })
  }
}

window.addEventListener('hashchange', render)
render()
