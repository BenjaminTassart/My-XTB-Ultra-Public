import React, { useState } from 'react'
import { api } from '../api.js'

const options = {
  favorites: ['Les favoris', 'Les favoris seront supprimés sur tous tes appareils.'],
  positions: ['Les positions', 'Toutes les positions seront supprimées. Les alertes seront conservées.'],
  alerts: ['Les alertes', 'Toutes les alertes et leur historique d’envoi seront supprimés.'],
  personal: ['Toutes les données personnelles', 'Favoris, positions, alertes, résumés IA et abonnements aux notifications seront supprimés sur tous tes appareils. Les quotas et les données de marché sont conservés.'],
}
export default function DataSettings({ onDeleted }) {
  const [scope, setScope] = useState('favorites')
  const [confirm, setConfirm] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  async function exportData() {
    setBusy(true); setMessage('')
    try {
      const data = await api.request('/data/export')
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const a = document.createElement('a'); a.href = url; a.download = 'my-xtb-ultra-' + new Date().toISOString().slice(0, 10) + '.json'
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000)
      setMessage('Export préparé. Vérifie que le fichier est enregistré dans tes téléchargements.')
    } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  async function erase(e) {
    e.preventDefault(); setBusy(true); setMessage('')
    try {
      await api.request('/data/delete', { method: 'POST', body: { scope, confirmation: confirm } })
      setConfirm(''); setOpen(false); setMessage('Suppression effectuée.'); onDeleted()
    } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  return <div className="card pad">
    <p>Exporter les favoris, positions, alertes et résumés IA dans un fichier JSON, sans clé API ni code d’accès.</p>
    <button className="btn" disabled={busy} onClick={exportData}>Exporter mes données</button>
    <p className="muted">Conserve le fichier en lieu sûr : il contient ton portefeuille. Cet export ne remplace pas une sauvegarde complète de la base. Il n’y a pas encore d’import automatique.</p>
    <button className="btn danger" disabled={busy} onClick={() => { setOpen(!open); setConfirm('') }}>Supprimer des données…</button>
    {open && <form className="portfolio-form" onSubmit={erase}>
      <label>Données à supprimer<select className="input" value={scope} disabled={busy} onChange={e => { setScope(e.target.value); setConfirm('') }}>{Object.entries(options).map(([id, [label]]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <p className="banner">{options[scope][1]} Cette action est irréversible dans l’application. Exporte tes données avant de continuer.</p>
      <label>Saisir SUPPRIMER pour confirmer<input className="input" value={confirm} disabled={busy} autoComplete="off" onChange={e => setConfirm(e.target.value)} /></label>
      <div className="chips"><button className="btn danger" disabled={busy || confirm !== 'SUPPRIMER'}>Confirmer la suppression</button><button className="btn" type="button" disabled={busy} onClick={() => setOpen(false)}>Annuler</button></div>
    </form>}
    {message && <p className="banner" role="status">{message}</p>}
  </div>
}
