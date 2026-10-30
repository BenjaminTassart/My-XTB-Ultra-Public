import { useEffect, useState, useSyncExternalStore } from 'react'
import { api } from './api.js'

// Devise d'affichage (euro par defaut), choisie sur l'accueil et la fiche, retenue sur l'appareil.
const KEY = 'xtb_currency'
const saved = localStorage.getItem(KEY)
let display = saved === 'USD' || saved === 'EUR' ? saved : 'EUR'
const listeners = new Set()
const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l) }

export function setDisplayCurrency(c) {
  display = c
  localStorage.setItem(KEY, c)
  listeners.forEach((l) => l())
}

export function useDisplayCurrency() {
  const c = useSyncExternalStore(subscribe, () => display)
  return [c, setDisplayCurrency]
}

const rates = new Map()
const pending = new Map()

function loadRate(from, to) {
  const k = from + '>' + to
  if (rates.has(k)) return Promise.resolve(rates.get(k))
  if (!pending.has(k)) {
    pending.set(k, api.fx(from, to).then((d) => { rates.set(k, d.rate); return d.rate }).finally(() => pending.delete(k)))
  }
  return pending.get(k)
}

// Renvoie { rate, currency } : le taux a appliquer aux prix et la devise a afficher.
// Tant que le taux n'est pas charge (ou s'il echoue), on affiche la devise d'origine sans conversion.
export function useRate(native) {
  const [shown] = useDisplayCurrency()
  const [, tick] = useState(0)
  const key = native + '>' + shown
  const needed = Boolean(native) && native !== shown

  useEffect(() => {
    if (!needed || rates.has(key)) return undefined
    let alive = true
    loadRate(native, shown).then(() => alive && tick((n) => n + 1)).catch(() => {})
    return () => { alive = false }
  }, [needed, key, native, shown])

  if (!native) return { rate: 1, currency: null }
  if (native === shown) return { rate: 1, currency: native }
  if (rates.has(key)) return { rate: rates.get(key), currency: shown }
  return { rate: 1, currency: native }
}
