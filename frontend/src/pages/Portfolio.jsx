import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { useDisplayCurrency } from '../currency.js'
import CurrencyToggle from '../components/CurrencyToggle.jsx'
import NotificationSettings from '../components/NotificationSettings.jsx'
import { money, quantity } from '../format.js'

const empty = { symbol: '', quantity: '', amount: '', mode: 'quantity', exchange_rate: '', entry_price: '', currency: 'EUR', threshold: '', direction: 'above' }

export default function Portfolio() {
  const [currency] = useDisplayCurrency()
  const formRef = useRef(null)

  const [data, setData] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [form, setForm] = useState(null)
  useEffect(() => { if (form) formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }, [form?.kind, form?.id])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    setData(null)
    Promise.all([api.request('/portfolio?currency=' + currency), api.request('/alerts')])
      .then(([p, a]) => { if (active) { setData(p); setAlerts(a.items) } })
      .catch(e => active && setError(e.message))
    return () => { active = false }
  }, [currency, revision])

  async function action(work) {
    setBusy(true); setError(''); setMessage('')
    try { await work() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const reload = () => setRevision(v => v + 1)
  const field = (key) => ({ value: form[key], onChange: e => setForm({ ...form, [key]: e.target.value }) })
  async function save(e) {
    e.preventDefault()
    await action(async () => {
      const body = { symbol: form.symbol.trim().toUpperCase(), currency: form.currency }
      if (form.kind === 'positions') Object.assign(body, {
        [form.mode === 'amount' ? 'amount' : 'quantity']: Number(form[form.mode === 'amount' ? 'amount' : 'quantity']),
        entry_price: Number(form.entry_price), exchange_rate: form.exchange_rate === '' ? null : Number(form.exchange_rate),
      })
      else Object.assign(body, { threshold: Number(form.threshold), direction: form.direction })
      const saved = await api.request('/' + form.kind + (form.id ? '/' + form.id : ''), { method: form.id ? 'PUT' : 'POST', body })
      if (saved.conversion) setMessage(saved.conversion)
      setForm(null); reload()
    })
  }
  function remove(kind, item) {
    if (!window.confirm(`Supprimer ${kind === 'positions' ? 'la position' : 'l’alerte'} ${item.symbol} ?`)) return
    action(async () => { await api.request('/' + kind + '/' + item.id, { method: 'DELETE' }); reload() })
  }
  return <>
    <div className="head-row"><h1>Portefeuille</h1><CurrencyToggle /></div>
    <p className="muted">Tes positions virtuelles, partagées entre tes appareils.</p>
    {error && <div className="banner error" role="alert">{error}<button className="chip" onClick={() => { setError(''); reload() }}>Réessayer</button></div>}
    {message && <div className="banner" role="status">{message}</div>}
    {data ? <div className="card pad">
      <span className="muted">{data.complete ? 'Valeur totale estimée' : 'Total indisponible · sous-total connu'}</span>
      <div className="price">{money(data.complete ? data.total : data.subtotal, data.currency)}</div>
      {!data.complete && <p className="down">Certaines positions ne peuvent pas être valorisées. Le sous-total les exclut.</p>}
      {data.stale && <p className="muted">Estimation avec des cours ou taux en cache périmés.</p>}
      <p className="muted">Conversion au taux du jour. Les cours peuvent être différés.</p>
    </div> : !error && <div className="spinner">Chargement du portefeuille…</div>}
    <div className="chips">
      <button className="btn primary" disabled={busy} onClick={() => setForm({ ...empty, kind: 'positions' })}>Ajouter une position</button>
      <button className="btn" disabled={busy} onClick={reload}>Actualiser</button>
    </div>
    {form && <form ref={formRef} className="card pad portfolio-form" onSubmit={save}>
      <h2>{form.id ? 'Modifier' : 'Ajouter'} {form.kind === 'positions' ? 'une position' : 'une alerte'}</h2>
      <label>Symbole<input className="input" required maxLength={15} placeholder="AAPL" {...field('symbol')} /></label>
      <label>{form.kind === 'positions' ? 'Devise du prix d’achat et du montant investi' : 'Devise de cotation'}<select className="input" {...field('currency')}>{['USD', 'EUR', 'CAD', 'GBP', 'CHF', 'JPY'].map(c => <option key={c}>{c}</option>)}</select></label>
      {form.kind === 'positions' ? <>
        <label>Saisir la position par<select className="input" {...field('mode')}><option value="quantity">Nombre d’actions</option><option value="amount">Montant investi</option></select></label>
        {form.mode === 'amount'
          ? <label>Montant investi hors frais ({form.currency})<input className="input" type="number" min="0.00000001" step="any" required {...field('amount')} /></label>
          : <label>Nombre d’actions<input className="input" type="number" min="0.00000001" step="any" required {...field('quantity')} /></label>}
        <label>Prix d’achat par action ({form.currency})<input className="input" type="number" min={form.mode === 'amount' ? '0.00000001' : '0'} step="any" required {...field('entry_price')} /></label>
        {form.mode === 'amount' && Number(form.entry_price) > 0 && Number(form.amount) > 0 && <p className="muted">Quantité calculée : {quantity(Number(form.amount) / Number(form.entry_price))} actions.</p>}
        <details><summary>Taux de change de mon achat (facultatif)</summary>
          <label>1 {form.currency} = combien d’unités de la devise de cotation ?<input className="input" type="number" min="0.00000001" step="any" placeholder="Automatique si vide" {...field('exchange_rate')} /></label>
        </details>
        <p className="muted">Le prix est enregistré dans la devise de cotation. Si elle diffère de ta saisie, conversion au taux disponible aujourd’hui : pour un achat passé, saisis le taux réellement appliqué. Le nombre d’actions est conservé.</p>
      </> : <>
        <label>Déclencher lorsque le cours est<select className="input" {...field('direction')}><option value="above">Supérieur ou égal au seuil</option><option value="below">Inférieur ou égal au seuil</option></select></label>
        <label>Seuil<input className="input" type="number" min="0.00000001" step="any" required {...field('threshold')} /></label>
        <p className="muted">Une seule alerte par seuil atteint. Modifier une alerte la réarme. Un seuil déjà atteint se déclenche à la prochaine vérification.</p>
      </>}
      {form.kind === 'alerts' && <p className="muted">Seuil dans la devise de cotation : USD pour AAPL, EUR pour MC.PA.</p>}
      <div className="chips"><button className="btn primary" disabled={busy}>Enregistrer</button><button type="button" className="btn" disabled={busy} onClick={() => setForm(null)}>Annuler</button></div>
    </form>}
    <h2>Positions</h2>
    {data?.items.length === 0 && <div className="card empty">Aucune position. Ajoute ton premier titre.</div>}
    {data?.items.map(p => <div className="card pad portfolio-item" key={p.id}>
      <div className="head-row"><strong>{p.symbol}</strong><strong>{money(p.value, data.currency)}</strong></div>
      <div className="muted">{quantity(p.quantity)} titres · entrée {money(p.entry_price, p.currency)}</div>
      {p.error && <p className="down">{p.error}</p>}{p.stale && <p className="muted">Cours ou taux périmé en cache.</p>}
      <div className="chips"><button className="chip" disabled={busy} onClick={() => setForm({ ...empty, ...p, kind: 'positions' })}>Modifier</button><button className="chip" disabled={busy} onClick={() => remove('positions', p)}>Supprimer</button></div>
    </div>)}
    <h2>Alertes de prix</h2>
    <p className="muted">Vérification automatique selon la planification configurée sur le serveur. Aucune garantie de détection des variations entre deux contrôles.</p>
    <div className="chips">
      <button className="btn" disabled={busy} onClick={() => setForm({ ...empty, kind: 'alerts' })}>Créer une alerte</button>
      <button className="btn" disabled={busy} onClick={() => action(async () => {
        const r = await api.request('/alerts/check', { method: 'POST' });
        setMessage(r.busy ? 'Vérification déjà en cours.' : `${r.triggered} alerte(s) déclenchée(s), ${r.sent} notification(s) envoyée(s). ${r.warnings.join(' ')}`); reload()
      })}>Vérifier maintenant</button>
    </div>
    <p className="muted">Sur iPhone, installer l’application sur l’écran d’accueil pour activer les notifications.</p>
    <NotificationSettings />
    {alerts.length === 0 && <div className="card empty">Aucune alerte.</div>}
    {alerts.map(a => <div className="card pad portfolio-item" key={a.id}>
      <strong>{a.symbol} {a.direction === 'above' ? '≥' : '≤'} {money(a.threshold, a.currency)}</strong>
      <p className={a.triggered_at ? 'up' : 'muted'}>{a.triggered_at ? `Déclenchée le ${new Date(a.triggered_at * 1000).toLocaleString('fr-FR')} · ${money(a.price, a.currency)}` : 'En attente du seuil'}</p>
      <div className="chips"><button className="chip" disabled={busy} onClick={() => setForm({ ...empty, ...a, kind: 'alerts' })}>Modifier / réarmer</button><button className="chip" disabled={busy} onClick={() => remove('alerts', a)}>Supprimer</button></div>
    </div>)}
  </>
}
