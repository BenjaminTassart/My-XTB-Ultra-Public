import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Logo } from '../components/StockSheet.jsx'
import { compact } from '../format.js'

const PRESETS = [ ['all', 'Tous'], ['value', 'Valorisation modérée'], ['growth', 'Profil croissance'], ['dividend', 'Dividendes'] ]
const DESCRIPTIONS = {
  all: 'Tri par capitalisation décroissante en dollars.',
  value: 'PER entre 0 et 20, P/B entre 0 et 3. Les valeurs nulles ou négatives sont exclues.',
  growth: 'PEG entre 0 et 2 et ROE supérieur à 15 %, plafonné à 1 000 %. Ce profil ne mesure pas directement la croissance du chiffre d’affaires.',
  dividend: 'Rendement du dividende déclaré supérieur ou égal à 2 %. Les données manquantes sont exclues.',
}

function StockList({ sector, region, preset, onOpen }) {
  const [data, setData] = useState(null)
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [next, setNext] = useState(null)
  const sentinel = useRef(null)
  const active = useRef(true)
  const pending = useRef(false)
  async function load(offset = 0) {
    if (pending.current) return
    pending.current = true; setLoading(true); setError('')
    try {
      const query = new URLSearchParams({ sector, region, preset, offset: String(offset) })
      const d = await api.request('/screener?' + query)
      if (!active.current) return
      setData(d); setNext(d.next_offset)
      setItems(old => offset === 0 ? d.items : [...new Map([...old, ...d.items].map(i => [i.symbol, i])).values()])
    } catch (e) { if (active.current) setError(e.message) }
    finally { pending.current = false; if (active.current) setLoading(false) }
  }
  useEffect(() => { active.current = true; load(); return () => { active.current = false } }, [])
  useEffect(() => {
    if (next == null || loading || error || !sentinel.current || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(entries => { if (entries[0].isIntersecting) load(next) }, { rootMargin: '200px' })
    observer.observe(sentinel.current)
    return () => observer.disconnect()
  }, [next, loading, error])
  return <>
    {data && <p className="muted">{data.total} résultat(s) · {data.loaded}/{data.universe_size} titres chargés. {data.failed > 0 ? `${data.failed} titre(s) avec un échec d’actualisation.` : ''}</p>}
    {error && <div className="banner error" role="alert">{error}<button className="chip" onClick={() => load(next ?? 0)}>Réessayer</button></div>}
    {items.map(s => <button className="row" key={s.symbol} onClick={() => onOpen(s.symbol)}>
      <Logo src={s.logo} label={s.symbol} />
      <div className="row-main"><div className="row-title">{s.name || s.symbol}</div><div className="row-sub">{s.symbol} · {s.country || 'Pays non renseigné'}</div>
        <small className="muted">Données enregistrées le {new Date(s.updated_at * 1000).toLocaleString('fr-FR')}{s.outdated ? ' · à actualiser' : ''}{s.refresh_error ? ' · dernier chargement en échec' : ''}</small>
      </div><div className="row-end"><div className="big">{compact(s.marketCap)} $</div><small className="muted">Capitalisation</small></div>
    </button>)}
    {!loading && data && items.length === 0 && <div className="card empty">Aucun titre chargé ne correspond à ces critères. Charge un lot ou essaie un autre filtre.</div>}
    {loading && <div className="spinner">Chargement de la liste…</div>}
    <div ref={sentinel} />
    {next != null && <button className="btn" disabled={loading} onClick={() => load(next)}>Charger les suivants</button>}
  </>
}

export default function Search({ onOpen }) {
  const [value, setValue] = useState('')
  const [sector, setSector] = useState('')
  const [region, setRegion] = useState('all')
  const [preset, setPreset] = useState('all')
  const [meta, setMeta] = useState(null)
  const [version, setVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let alive = true
    api.request('/screener').then(d => { if (alive) setMeta(d) }).catch(e => { if (alive) setNotice(e.message) })
    return () => { alive = false }
  }, [version])
  function submit(e) { e.preventDefault(); if (value.trim()) onOpen(value.trim().toUpperCase()) }
  async function refresh() {
    setBusy(true); setNotice('')
    try {
      const d = await api.request('/screener/refresh', { method: 'POST' })
      setNotice(d.busy ? 'Un chargement est déjà en cours.' : `${d.updated} titre(s) actualisé(s), ${d.calls} appel(s) compté(s). ${d.warnings.join(' ')}`)
      setVersion(v => v + 1)
    } catch (e) { setNotice(e.message) } finally { setBusy(false) }
  }
  return <>
    <h1>Recherche</h1>
    <form className="form" onSubmit={submit}><input className="input" value={value} placeholder="Symbole : AAPL, MSFT…" aria-label="Symbole boursier" autoCapitalize="characters" autoCorrect="off" spellCheck="false" onChange={e => setValue(e.target.value)} /><button className="btn primary" disabled={!value.trim()}>Voir</button></form>
    <h2>Explorer par secteur</h2>
    <p className="muted">Sélection de 55 grandes entreprises cotées aux États-Unis, couvrant onze secteurs. Ce n’est pas l’ensemble du marché. Les filtres utilisent uniquement les données déjà enregistrées.</p>
    <div className="chips" role="group" aria-label="Secteur">
      <button className="chip" aria-pressed={sector === ''} onClick={() => setSector('')}>Tous les secteurs</button>
      {meta?.sectors.map(s => <button className="chip" key={s.id} aria-pressed={sector === s.id} onClick={() => setSector(s.id)}>{s.label}</button>)}
    </div>
    <div className="portfolio-form">
      <label>Pays du siège, selon le fournisseur<select className="input" value={region} onChange={e => setRegion(e.target.value)}><option value="all">Toutes les zones</option><option value="US">États-Unis</option><option value="other">Hors États-Unis (cotations américaines)</option></select></label>
    </div>
    <div className="chips" role="group" aria-label="Filtres prêts à l’emploi">{PRESETS.map(([id, label]) => <button className="chip" key={id} aria-pressed={preset === id} onClick={() => setPreset(id)}>{label}</button>)}</div>
    <p className="muted">{DESCRIPTIONS[preset]} Ces critères servent à explorer les données, pas à recommander un achat.</p>
    <div className="card pad" style={{ marginBottom: 20 }}>
      <p className="muted">{meta ? `${meta.loaded}/${meta.universe_size} titres chargés · budget recherche : ${meta.daily_calls}/${meta.daily_budget} appels aujourd’hui (UTC).` : 'Lecture de la couverture…'} La consultation des listes ne consomme aucun appel financier.</p>
      <button className="btn" disabled={busy} onClick={refresh}>{busy ? 'Chargement du lot…' : 'Charger / actualiser jusqu’à 5 titres'}</button>
      <p className="muted">Le chargement d’un lot peut prendre plusieurs minutes. Une fois enregistrés, les titres sont filtrés localement. Les titres les moins récemment essayés passent en premier.</p>
      {notice && <div className="banner" role="status">{notice}</div>}
    </div>
    <StockList key={`${sector}:${region}:${preset}:${version}`} sector={sector} region={region} preset={preset} onOpen={onOpen} />
  </>
}
