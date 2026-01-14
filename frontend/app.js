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
  if (t === 'image/jpeg' || t === 'image/png' || t === 'image/gif' || t === 'image/tiff') return true
  const name = (f.name || '').toLowerCase()
  return (
    name.endsWith('.jpg') ||
    name.endsWith('.jpeg') ||
    name.endsWith('.png') ||
    name.endsWith('.gif') ||
    name.endsWith('.tif') ||
    name.endsWith('.tiff')
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
            <button data-extract="${d.id}" data-kind="${escapeHtml(d.file_kind || '')}" class="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium hover:bg-blue-500">Ekstrak</button>
            ${d.file_kind === 'image' ? `<button data-mto="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">OCR MTO</button>` : ''}
            ${d.file_kind === 'image' ? `<button data-mto-csv="${d.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">MTO CSV</button>` : ''}
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
        <div class="mt-1 text-xs text-slate-400">PDF untuk ekstraksi, atau gambar (JPG/JPEG/PNG) untuk preview.</div>
        <div class="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/30 p-4">
          <input id="file" type="file" accept="application/pdf,image/png,image/jpeg,image/gif,image/tiff" class="block w-full text-sm" />
          <div id="img-preview" class="mt-3 hidden overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40"></div>
          <button id="btn-upload" class="mt-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium hover:bg-blue-500">Upload</button>
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
          <input id="mat-q" placeholder="Cari..." class="w-44 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <input id="mat-size" placeholder="Size" class="w-28 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <input id="mat-unit" placeholder="Unit" class="w-24 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
          <select id="mat-limit" class="w-24 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40">
            <option value="50">50</option>
            <option value="200" selected>200</option>
            <option value="500">500</option>
          </select>
          <button id="btn-search" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:bg-slate-800">Terapkan</button>
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
  return (materials || [])
    .map(
      (m) => `
      <tr class="border-t border-slate-800/60">
        <td class="px-3 py-3 align-top">
          <div class="text-sm font-medium">${escapeHtml(m.description)}</div>
        </td>
        <td class="px-3 py-3 align-top">${specBulletsHtml(m.spec)}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${escapeHtml(m.size || '-')}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${m.quantity == null ? '-' : m.quantity}</td>
        <td class="px-3 py-3 align-top text-sm text-slate-300">${escapeHtml(m.unit || '-')}</td>
        <td class="px-3 py-3 text-right">
          <button data-del-mat="${m.id}" class="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs hover:bg-slate-800">Hapus</button>
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
        sortBy: 'created_at',
        sortDir: 'desc',
        limit: 200,
        offset: 0,
        nextOffset: null
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
        matState.q = qs('#mat-q').value.trim()
        matState.size = qs('#mat-size').value.trim()
        matState.unit = qs('#mat-unit').value.trim()
        matState.limit = parseInt(qs('#mat-limit').value, 10) || 200
        await loadMaterials(true)
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
      if (fileEl && previewEl) {
        fileEl.addEventListener('change', async () => {
          previewEl.classList.add('hidden')
          previewEl.innerHTML = ''
          const f = fileEl.files && fileEl.files[0]
          if (!f || !isImageFile(f)) return
          const url = URL.createObjectURL(f)
          previewEl.innerHTML = `<img src="${url}" class="max-h-56 w-full object-contain" />`
          previewEl.classList.remove('hidden')
        })
      }

      qs('#btn-upload').addEventListener('click', async () => {
        const f = qs('#file').files[0]
        const statusEl = qs('#upload-status')
        if (!f) {
          toast('Pilih file dulu', 'error')
          return
        }

        if (!(isPdfFile(f) || isImageFile(f))) {
          toast('Format tidak didukung. Gunakan PDF/JPG/JPEG/PNG/GIF/TIFF', 'error')
          return
        }

        if (isImageFile(f)) {
          const max = 5 * 1024 * 1024
          if (f.size > max) {
            toast('Ukuran file melebihi 5MB', 'error')
            return
          }
          try {
            const { width, height } = await getImageResolution(f)
            if (width < 300 || height < 300) {
              toast('Resolusi minimal 300x300 piksel', 'error')
              return
            }
          } catch (e) {
            toast(e.message, 'error')
            return
          }
        }

        statusEl.textContent = 'Uploading...'
        const form = new FormData()
        form.append('file', f)
        try {
          await api(`/api/projects/${projectId}/documents`, { method: 'POST', body: form })
          toast('Upload berhasil', 'success')
          statusEl.textContent = ''
          render()
        } catch (e) {
          statusEl.textContent = ''
          toast(e.message, 'error')
        }
      })
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
          const kind = (btn.getAttribute('data-kind') || '').toLowerCase()
          if (kind === 'image') {
            const out = qs(`[data-doc-out="${id}"]`)
            if (out) {
              out.classList.add('hidden')
              out.textContent = ''
            }
            try {
              toast('Menjalankan OCR MTO...', 'info')
              const res = await api(`/api/documents/${id}/mto`, { method: 'POST' })
              const items = (res && res.items) || []
              const outputs = (res && res.outputs) || {}
              const txtUrl = outputs.txt && outputs.txt.download_url
              const csvUrl = outputs.csv && outputs.csv.download_url
              if (out) {
                const links = []
                if (txtUrl) links.push(`<a class="underline" target="_blank" href="${txtUrl}">Download TXT</a>`)
                if (csvUrl) links.push(`<a class="underline" target="_blank" href="${csvUrl}">Download CSV</a>`)
                out.innerHTML = `${links.length ? `<div class="mb-2 flex gap-3">${links.join('')}</div>` : ''}<pre class="whitespace-pre-wrap">${escapeHtml(
                  JSON.stringify(items, null, 2)
                )}</pre>`
                out.classList.remove('hidden')
              }
              toast(`OCR MTO selesai: ${items.length} baris`, 'success')
            } catch (e) {
              toast(e.message, 'error')
            }
            return
          }
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

      qsa('[data-mto]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.getAttribute('data-mto')
          if (!id) return
          const out = qs(`[data-doc-out="${id}"]`)
          if (out) {
            out.classList.add('hidden')
            out.textContent = ''
          }
          try {
            toast('Menjalankan OCR MTO...', 'info')
            const res = await api(`/api/documents/${id}/mto`, { method: 'POST' })
            const items = (res && res.items) || []
            const outputs = (res && res.outputs) || {}
            const txtUrl = outputs.txt && outputs.txt.download_url
            const csvUrl = outputs.csv && outputs.csv.download_url
            if (out) {
              const links = []
              if (txtUrl) links.push(`<a class="underline" target="_blank" href="${txtUrl}">Download TXT</a>`)
              if (csvUrl) links.push(`<a class="underline" target="_blank" href="${csvUrl}">Download CSV</a>`)
              out.innerHTML = `${links.length ? `<div class="mb-2 flex gap-3">${links.join('')}</div>` : ''}<pre class="whitespace-pre-wrap">${escapeHtml(
                JSON.stringify(items, null, 2)
              )}</pre>`
              out.classList.remove('hidden')
            }
            toast(`OCR MTO selesai: ${items.length} baris`, 'success')
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
