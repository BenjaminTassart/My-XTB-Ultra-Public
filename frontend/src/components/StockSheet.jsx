import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { compact, indicatorValue, money, num, signedPct, trend } from '../format.js'
import Icon from './Icon.jsx'
import Results from './Results.jsx'
import PriceChart from './PriceChart.jsx'
import CurrencyToggle from './CurrencyToggle.jsx'
import { useRate } from '../currency.js'

function Logo({ src, label }) {
  const [broken, setBroken] = useState(false)
  if (!src || broken) return <div className="logo">{(label || '?').slice(0, 2)}</div>
  return <img className="logo" src={src} alt="" onError={() => setBroken(true)} />
}

export { Logo }

export default function StockSheet({ symbol, onClose, onFavoritesChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
    setData(null); setError(null)
    api.stock(symbol).then((d) => alive && setData(d)).catch((e) => alive && setError(e))
    return () => { alive = false }
  }, [symbol])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function toggleFavorite() {
    if (!data || busy) return
    setBusy(true)
    try {
      if (data.favorite) await api.removeFavorite(symbol)
      else await api.addFavorite(symbol)
      setData({ ...data, favorite: !data.favorite })
      onFavoritesChanged()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const { rate, currency: shown } = useRate(data?.currency)
  const cv = (v) => (v == null ? null : v * rate)
  const t = trend(data?.change)

  return (
    <div className="backdrop" onClick={onClose}>
      <aside className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Fiche ${symbol}`}>
        <div className="sheet-top">
          <button className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
          {data && (
            <button className={'icon-btn' + (data.favorite ? ' on' : '')} onClick={toggleFavorite} disabled={busy}
                    aria-label={data.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'}>
              <Icon name="star" filled={data.favorite} />
            </button>
          )}
        </div>

        {!data && !error && <div className="spinner">Chargement…</div>}
        {error && !data && (
          <div className={'banner' + (error.code === 'quota' || error.code === 'payant' ? '' : ' error')}>
            {error.message}
          </div>
        )}

        {data && (
          <>
            <div className="sheet-head">
              <Logo src={data.logo} label={data.symbol} />
              <div>
                <div className="sheet-name">{data.name}</div>
                <div className="muted">{data.symbol}{data.exchange ? ' · ' + data.exchange : ''}</div>
              </div>
            </div>

            {(data.quote_stale ?? data.stale) && (
              <div className="banner" style={{ marginTop: 16 }}>
                Données en cache : le fournisseur est momentanément indisponible.
              </div>
            )}
            {error && <div className="banner error" style={{ marginTop: 16 }}>{error.message}</div>}

            <div className="price-row">
              <div>
                <div className="price">{money(cv(data.price), shown)}</div>
                <div className={t}>
                  {data.change != null && (data.change > 0 ? '+' : '') + num(cv(data.change))} ({signedPct(data.changePercent)})
                </div>
              </div>
              {data.currency && <CurrencyToggle />}
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              Prix différé d'environ 15 minutes{rate !== 1 ? ` · converti de ${data.currency} au taux du jour` : ''}
              {data.quote_source === 'twelvedata' ? ' · Source : Twelve Data' : ''}
            </div>

            <h2>Graphique</h2>
            <PriceChart symbol={symbol} factor={rate} />
            <Results key={symbol} symbol={symbol} />


            {data.indicators.length > 0 && (
              <>
                <h2>Indicateurs</h2>
                <p className="muted">Source : {data.indicators_source || 'FMP'}. « Non disponible » indique une donnée absente, pas une valeur nulle.</p>
                {data.indicators_note && <p className="muted">{data.indicators_note}</p>}
                {data.indicators_url && <p><a href={data.indicators_url} target="_blank" rel="noopener noreferrer">Consulter le dépôt SEC utilisé</a></p>}
                {data.indicators_stale && <p className="muted">Dernières valeurs enregistrées : actualisation indisponible, indicateurs à vérifier.</p>}
                <div className="grid">
                  {data.indicators.map((i) => (
                    <div className="stat" key={i.key}>
                      <div className="stat-label">{i.label}</div>
                      <div className="stat-value">{i.value == null ? 'Non disponible' : indicatorValue(i)}</div>
                      {i.source && <small className="muted">{i.source}</small>}
                      {i.reason && <p className="muted" style={{ fontSize: 12 }}>{i.reason}</p>}
                    </div>
                  ))}
                  <div className="stat">
                    <div className="stat-label">{data.marketCapLabel || 'Capitalisation'}</div>
                    <div className="stat-value">{compact(cv(data.marketCap))}{data.marketCap != null && shown ? ' ' + shown : ''}</div>
                  </div>
                </div>
              </>
            )}

            <h2>Séance et 52 semaines</h2>
            <div className="grid">
              <div className="stat"><div className="stat-label">Plus bas du jour</div><div className="stat-value">{num(cv(data.dayLow))}</div></div>
              <div className="stat"><div className="stat-label">Plus haut du jour</div><div className="stat-value">{num(cv(data.dayHigh))}</div></div>
              <div className="stat"><div className="stat-label">Plus bas 52 sem.</div><div className="stat-value">{num(cv(data.yearLow))}</div></div>
              <div className="stat"><div className="stat-label">Plus haut 52 sem.</div><div className="stat-value">{num(cv(data.yearHigh))}</div></div>
            </div>

            {(data.sector || data.description) && (
              <>
                <h2>À propos</h2>
                {data.sector && <p className="muted">{[data.sector, data.industry, data.country].filter(Boolean).join(' · ')}</p>}
                {data.description && <p className="desc">{data.description.slice(0, 420)}{data.description.length > 420 ? '…' : ''}</p>}
              </>
            )}
            {data.warnings.some(w => w.section === 'profile') && <p className="muted">Profil de l’entreprise indisponible.</p>}
            {data.warnings.some(w => w.section) && <details className="muted">
              <summary>Détails des données indisponibles</summary>
              {data.warnings.filter(w => w.section).map((w, i) => <p key={i}>
                {w.section === 'profile' ? 'Profil' : 'Indicateurs'} : {w.message}
              </p>)}
            </details>}
          </>
        )}
      </aside>
    </div>
  )
}
