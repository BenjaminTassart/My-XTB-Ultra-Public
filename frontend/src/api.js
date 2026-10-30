const KEY = 'xtb_access_code'

export const getCode = () => localStorage.getItem(KEY) || ''
export const setCode = (c) => localStorage.setItem(KEY, c)
export const clearCode = () => localStorage.removeItem(KEY)

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let res
  try {
    res = await fetch('/api' + path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Access-Code': getCode() },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'reseau', "Impossible de joindre le serveur. Il se réveille peut-être : réessaie dans une minute.")
  }
  let data = null
  try { data = await res.json() } catch { /* pas de JSON */ }
  if (!res.ok) {
    const d = data && data.detail
    const obj = d && typeof d === 'object' && !Array.isArray(d) ? d : null
    const code = obj?.code || 'erreur'
    const message = obj?.message || (typeof d === 'string' ? d : 'Erreur inattendue.')
    if (res.status === 401) window.dispatchEvent(new Event('xtb-unauthorized'))
    if (code === 'quota') window.dispatchEvent(new CustomEvent('xtb-quota', { detail: message }))
    throw new ApiError(res.status, code, message)
  }
  return data
}

export const api = {
  request,
  check: () => request('/auth/check'),
  favorites: () => request('/favorites'),
  addFavorite: (symbol) => request('/favorites', { method: 'POST', body: { symbol } }),
  removeFavorite: (symbol) => request('/favorites/' + encodeURIComponent(symbol), { method: 'DELETE' }),
  stock: (symbol) => request('/stock/' + encodeURIComponent(symbol)),
  news: () => request('/news'),
  history: (symbol) => request('/history/' + encodeURIComponent(symbol)),
  fx: (from, to) => request('/fx?from=' + from + '&to=' + to),
  quota: () => request('/quota'),
}
