// Indicateurs techniques calcules dans le navigateur : aucun appel d'API supplementaire.

export function sma(values, n) {
  const out = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= n) sum -= values[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

// RSI de Wilder (14 periodes par defaut)
export function rsi(values, n = 14) {
  const out = new Array(values.length).fill(null)
  if (values.length <= n) return out
  let gain = 0
  let loss = 0
  for (let i = 1; i <= n; i++) {
    const d = values[i] - values[i - 1]
    gain += Math.max(d, 0)
    loss += Math.max(-d, 0)
  }
  let ag = gain / n
  let al = loss / n
  out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al)
  for (let i = n + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1]
    ag = (ag * (n - 1) + Math.max(d, 0)) / n
    al = (al * (n - 1) + Math.max(-d, 0)) / n
    out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al)
  }
  return out
}
