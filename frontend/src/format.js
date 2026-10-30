const nf = (d) => new Intl.NumberFormat('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d })

export const num = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : nf(d).format(v))
export const pct = (fraction, d = 2) => (fraction == null ? '—' : nf(d).format(fraction * 100) + ' %')
export const signedPct = (v) => (v == null ? '—' : (v > 0 ? '+' : '') + nf(2).format(v) + ' %')
export const compact = (v) =>
  v == null ? '—' : new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 2 }).format(v)

export const quantity = (v) => v == null ? '—' : new Intl.NumberFormat('fr-FR', { maximumSignificantDigits: 15 }).format(v)

export function compactMoney(v, currency) {
  if (v == null) return '—'
  if (!currency) return compact(v)
  return new Intl.NumberFormat('fr-FR', { notation: 'compact', style: 'currency', currency, maximumFractionDigits: 2 }).format(v)
}

export function money(v, currency) {
  if (v == null) return '—'
  if (!currency) return num(v)
  try {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency }).format(v)
  } catch {
    return num(v)
  }
}

export const trend = (v) => (v == null || v === 0 ? 'flat' : v > 0 ? 'up' : 'down')

export function indicatorValue(ind) {
  if (ind.value == null) return '—'
  if (ind.kind === 'percent') return pct(ind.value)
  return num(ind.value)
}

export function timeAgo(ts) {
  if (!ts) return ''
  const m = Math.round((Date.now() / 1000 - ts) / 60)
  if (m < 60) return `il y a ${Math.max(m, 1)} min`
  const h = Math.round(m / 60)
  return h < 24 ? `il y a ${h} h` : `il y a ${Math.round(h / 24)} j`
}
