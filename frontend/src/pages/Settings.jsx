import React, { useEffect, useState } from 'react'
import NotificationSettings from '../components/NotificationSettings.jsx'
import DataSettings from '../components/DataSettings.jsx'
import { getTheme, setTheme } from '../theme.js'
import { api, clearCode } from '../api.js'

export default function Settings({ onLogout, onDataChanged }) {
  const [theme, chooseTheme] = useState(getTheme)
  const [notificationVersion, setNotificationVersion] = useState(0)
  const [quota, setQuota] = useState(null)
  const [error, setError] = useState('')
  const [diagnosing, setDiagnosing] = useState(false)
  const [diagnosis, setDiagnosis] = useState('')
  async function diagnose() {
    setDiagnosing(true); setDiagnosis('')
    try { const r = await api.request('/quota/alphavantage/diagnose', { method: 'POST' }); setDiagnosis(r.message) }
    catch (e) { setDiagnosis(e.message) }
    finally { await refresh(); setDiagnosing(false) }
  }
  const refresh = () => { setError(''); return api.quota().then(d => setQuota(d.providers)).catch(e => setError(e.message)) }

  useEffect(() => { refresh() }, [])

  function logout() {
    clearCode()
    onLogout()
  }

  return (
    <>
      <h1>Paramètres</h1>
      <h2>Apparence</h2>
      <div className="card pad"><label>Thème de cet appareil<select className="input" value={theme} onChange={e => { chooseTheme(e.target.value); setTheme(e.target.value) }}><option value="dark">Sombre</option><option value="light">Clair</option><option value="system">Selon l’appareil</option></select></label><p className="muted">Ce choix est conservé sur cet appareil.</p></div>
      <h2>Notifications</h2>
      <NotificationSettings key={notificationVersion} />
      <h2>Mes données</h2>
      <DataSettings onDeleted={() => { setNotificationVersion(v => v + 1); onDataChanged?.() }} />

      <h2 style={{ marginTop: 6 }}>Quota des API gratuites (aujourd'hui)</h2>
      <button className="btn" onClick={refresh}>Actualiser les compteurs</button>
      {diagnosis && <p className="banner" role="status">{diagnosis}</p>}
      {error && <p className="down" role="alert">{error}</p>}
      <p className="muted">Compteurs locaux, pas le solde du compte fournisseur. Les anciennes valeurs peuvent inclure un refus compté comme un quota plein.</p>
      {!quota && !error && <div className="spinner">Chargement…</div>}
      {quota && quota.map((q) => (
        <div className="card pad" key={q.provider} style={{ marginBottom: 10 }}>
          <div className="setting" style={{ padding: 0, border: 0 }}>
            <span>{q.name}</span>
            <span className={q.exhausted ? 'down' : 'muted'}>{q.used} / {q.limit}</span>
          </div>
          <div className={'meter' + (q.exhausted ? ' full' : '')}>
            <div style={{ width: (q.limit > 0 ? Math.min(100, (q.used / q.limit) * 100) : 0) + '%' }} />
          </div>
          <p className="muted">Remise à zéro locale : {new Date(q.reset_at).toLocaleString('fr-FR')} (heure de cet appareil).</p>
          {q.exhausted && <p className="down">{q.provider_blocked ? 'Limite signalée par le fournisseur : les appels sont temporairement suspendus.' : 'Limite locale atteinte.'} Les données en cache restent affichées.</p>}
          {q.provider === 'alphavantage' && q.provider_blocked && !q.last_refusal && <div>
            <p className="muted">Ancien refus sans détail enregistré. Un diagnostic unique consomme au maximum un appel, sans remettre le compteur à zéro.</p>
            <button className="btn" disabled={diagnosing || q.used >= q.limit} onClick={diagnose}>{diagnosing ? 'Diagnostic en cours…' : 'Préciser ce refus'}</button>
          </div>}
          {q.provider_blocked && q.retry_at && <p className="muted">Nouvel essai possible après {new Date(q.retry_at * 1000).toLocaleString('fr-FR')}, dans la limite du compteur quotidien local.</p>}
          {q.last_refusal && <p className="muted" style={{ overflowWrap: 'anywhere' }}>Dernier refus enregistré ({new Date(q.last_refusal_at * 1000).toLocaleString('fr-FR')}) : {q.last_refusal}</p>}
          {q.provider_blocked && <p className="muted">La remise à zéro locale ne garantit pas que le fournisseur autorisera de nouveaux appels.</p>}
        </div>
      ))}

      <h2>Accès</h2>
      <div className="card pad">
        <div className="setting">
          <span>Code d'accès enregistré sur cet appareil</span>
          <button className="btn" onClick={logout}>Se déconnecter</button>
        </div>
      </div>


    </>
  )
}
