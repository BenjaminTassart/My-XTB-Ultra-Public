import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Logo } from '../components/StockSheet.jsx'
import { money, signedPct, timeAgo, trend } from '../format.js'
import { useRate } from '../currency.js'
import CurrencyToggle from '../components/CurrencyToggle.jsx'

function FavRow({ f, onOpen }) {
  const { rate, currency } = useRate(f.currency)
  return (
    <button className="row" onClick={() => onOpen(f.symbol)}>
      <Logo src={f.logo} label={f.symbol} />
      <div className="row-main">
        <div className="row-title">{f.symbol}</div>
        <div className="row-sub">{f.error ? f.error.message : f.name}</div>
      </div>
      {!f.error && (
        <div className="row-end">
          <div className="big">{money(f.price == null ? null : f.price * rate, currency)}</div>
          <div className={trend(f.change)}>{signedPct(f.changePercent)}</div>
        </div>
      )}
    </button>
  )
}

export default function Home({ version, onOpen, onGoSearch }) {
  const [favs, setFavs] = useState(null)
  const [favError, setFavError] = useState(null)
  const [news, setNews] = useState(null)

  useEffect(() => {
    let alive = true
    setFavError(null)
    api.favorites().then((d) => alive && setFavs(d.items)).catch((e) => alive && setFavError(e))
    api.news().then((d) => alive && setNews(d.items)).catch(() => alive && setNews([]))
    return () => { alive = false }
  }, [version])

  return (
    <>
      <h1>Accueil</h1>

      <div className="head-row">
        <h2>Favoris</h2>
        <CurrencyToggle />
      </div>
      {favError && <div className="banner error">{favError.message}</div>}
      {!favs && !favError && <div className="spinner">Chargement…</div>}
      {favs && favs.length === 0 && (
        <div className="card empty">
          Aucun favori pour l'instant.
          <p><button className="btn" onClick={onGoSearch}>Chercher un titre</button></p>
        </div>
      )}
      {favs && favs.map((f) => <FavRow key={f.symbol} f={f} onOpen={onOpen} />)}

      <h2>Actualités</h2>
      {!news && <div className="spinner">Chargement…</div>}
      {news && news.length === 0 && <div className="card empty">Aucune actualité disponible pour le moment.</div>}
      {news && news.length > 0 && (
        <div className="card news">
          {news.map((n) => (
            <a key={n.link} href={n.link} target="_blank" rel="noopener noreferrer">
              <div className="news-title">{n.title}</div>
              <div className="news-meta">{[n.source, timeAgo(n.ts)].filter(Boolean).join(' · ')}</div>
            </a>
          ))}
        </div>
      )}
    </>
  )
}
