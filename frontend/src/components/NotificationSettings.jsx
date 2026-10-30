import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function NotificationSettings() {
  const [config, setConfig] = useState(null)
  const [subscribed, setSubscribed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const c = await api.request('/push/config')
        if (alive) setConfig(c)
        if (!supported) return
        const reg = await navigator.serviceWorker.getRegistration()
        const sub = await reg?.pushManager.getSubscription()
        if (sub) {
          const status = await api.request('/push/status', { method: 'POST', body: sub.toJSON() })
          if (alive) setSubscribed(status.subscribed)
        }
      } catch (e) { if (alive) setMessage(e.message) }
    }
    load(); return () => { alive = false }
  }, [])
  async function toggle() {
    setBusy(true); setMessage('')
    try {
      if (!subscribed && await Notification.requestPermission() !== 'granted') throw new Error('Autorisation refusée. Modifie les réglages du navigateur pour autoriser les notifications.')
      await navigator.serviceWorker.register('/sw.js')
      const reg = await navigator.serviceWorker.ready
      let sub = await reg.pushManager.getSubscription()
      if (subscribed) {
        if (sub) {
          await api.request('/push/unsubscribe', { method: 'POST', body: sub.toJSON() })
          await sub.unsubscribe()
        }
        setSubscribed(false); setMessage('Notifications désactivées sur cet appareil.')
      } else {
        const key = config.publicKey.replace(/-/g, '+').replace(/_/g, '/')
        const bytes = Uint8Array.from(atob(key + '='.repeat((4 - key.length % 4) % 4)), c => c.charCodeAt(0))
        sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes })
        await api.request('/push/subscribe', { method: 'POST', body: sub.toJSON() })
        setSubscribed(true); setMessage('Notifications activées sur cet appareil.')
      }
    } catch (e) { setMessage(e.message) } finally { setBusy(false) }
  }
  return <div className="card pad">
    <p>{subscribed ? 'Notifications actives sur cet appareil.' : 'Notifications non activées sur cet appareil.'}</p>
    {!supported && <p className="muted">Ce navigateur ne propose pas les notifications. Sur iPhone, ouvrir l’application installée sur l’écran d’accueil.</p>}
    {config && !config.enabled && <p className="muted">Les clés de notification doivent être configurées sur le serveur (guide étape 3).</p>}
    <button className="btn" disabled={!supported || busy || (!subscribed && !config?.enabled)} onClick={toggle}>{busy ? 'En cours…' : subscribed ? 'Désactiver sur cet appareil' : 'Activer sur cet appareil'}</button>
    <p className="muted">Les alertes se gèrent dans Portefeuille. La vérification automatique dépend de la planification configurée sur le serveur.</p>
    {message && <p role="status" className="banner">{message}</p>}
  </div>
}
