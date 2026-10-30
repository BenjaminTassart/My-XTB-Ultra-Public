import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Nav from './components/Nav.jsx'
import LoginGate from './components/LoginGate.jsx'
import StockSheet from './components/StockSheet.jsx'
import Home from './pages/Home.jsx'
import Search from './pages/Search.jsx'
import Portfolio from './pages/Portfolio.jsx'
import Settings from './pages/Settings.jsx'

export default function App() {
  const [auth, setAuth] = useState('checking') // checking | needcode | wrongcode | ok | down
  const [tab, setTab] = useState(new URLSearchParams(window.location.search).get('tab') === 'portfolio' ? 'portfolio' : 'home')
  const [symbol, setSymbol] = useState(null)
  const [favVersion, setFavVersion] = useState(0)
  const [quotaMsg, setQuotaMsg] = useState(null)
  const [triedCode, setTriedCode] = useState(false)

  const check = useCallback(() => {
    setAuth('checking')
    api.check()
      .then(() => setAuth('ok'))
      .catch((e) => {
        if (e.status === 401) setAuth(triedCode ? 'wrongcode' : 'needcode')
        else setAuth('down')
      })
  }, [triedCode])

  useEffect(() => { check() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onQuota = (e) => setQuotaMsg(e.detail)
    const onUnauth = () => setAuth('needcode')
    window.addEventListener('xtb-quota', onQuota)
    window.addEventListener('xtb-unauthorized', onUnauth)
    return () => {
      window.removeEventListener('xtb-quota', onQuota)
      window.removeEventListener('xtb-unauthorized', onUnauth)
    }
  }, [])

  if (auth === 'checking') return <div className="center muted">Connexion…</div>
  if (auth === 'down') {
    return (
      <div className="center">
        <div className="login">
          <h1>My XTB Ultra</h1>
          <p className="muted">Le serveur ne répond pas. Il se réveille peut-être (jusqu'à une minute sur l'offre gratuite).</p>
          <button className="btn primary" onClick={check}>Réessayer</button>
        </div>
      </div>
    )
  }
  if (auth === 'needcode' || auth === 'wrongcode') {
    return <LoginGate wrong={auth === 'wrongcode'} onDone={() => { setTriedCode(true); check() }} />
  }

  const refreshFavs = () => setFavVersion((v) => v + 1)

  return (
    <div className="app">
      <Nav tab={tab} onChange={setTab} />
      <main className="main">
        {quotaMsg && <div className="banner" role="alert">{quotaMsg}</div>}
        {tab === 'home' && <Home version={favVersion} onOpen={setSymbol} onGoSearch={() => setTab('search')} />}
        {tab === 'search' && <Search onOpen={setSymbol} />}
        {tab === 'portfolio' && <Portfolio />}
        {tab === 'settings' && <Settings onDataChanged={refreshFavs} onLogout={() => { setTriedCode(false); setAuth('needcode') }} />}
      </main>
      {symbol && <StockSheet symbol={symbol} onClose={() => setSymbol(null)} onFavoritesChanged={refreshFavs} />}
    </div>
  )
}
