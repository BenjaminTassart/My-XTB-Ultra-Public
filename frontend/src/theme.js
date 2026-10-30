const KEY = 'xtb_theme'
export function getTheme() {
  try { const value = localStorage.getItem(KEY); return ['dark', 'light', 'system'].includes(value) ? value : 'dark' } catch { return 'dark' }
}
export function applyTheme() {
  const selected = getTheme()
  document.documentElement.dataset.theme = selected === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : selected
}
export function setTheme(value) {
  try { localStorage.setItem(KEY, value) } catch { /* Stockage indisponible : préférence valable pour cette page. */ }
  document.documentElement.dataset.theme = value === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : value
}
applyTheme()
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (getTheme() === 'system') applyTheme() })
