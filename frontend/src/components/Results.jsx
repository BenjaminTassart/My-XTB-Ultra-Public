import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { money, compactMoney, signedPct, trend } from '../format.js'
import { useRate } from '../currency.js'
import CurrencyToggle from './CurrencyToggle.jsx'

function Publication({ row: r }) {
  const { rate, currency } = useRate(r.currency)
  return <div className="card pad portfolio-item">
    <strong>{r.period} · période close le {r.date} · {currency || 'devise non renseignée'}</strong>
    {currency && currency !== r.currency && <p className="muted">Converti de {r.currency} au taux actuel, pour la lecture uniquement.</p>}
    {[['revenue', 'Chiffre d’affaires'], ['netIncome', 'Résultat net'], ['eps', 'Bénéfice par action dilué']].map(([key, label]) => <div className="setting" key={key}>
      <span>{label}</span><span title={r[key] == null ? 'Non fourni' : money(r[key] * rate, currency)}>
        {r[key] == null ? 'Non fourni' : key === 'eps' ? money(r[key] * rate, currency) : compactMoney(r[key] * rate, currency)}
        <br /><small className={trend(r[key + 'Growth'])}>{signedPct(r[key + 'Growth'])}</small>
      </span>
    </div>)}
  </div>
}

function SummaryText({ text }) {
  // Rendu limité : React échappe le texte, aucun HTML fourni par le modèle n’est interprété.
  return <div style={{ lineHeight: 1.6 }}>{text.split(/\n\s*\n/).map((p, i) => <p key={i} style={{ whiteSpace: 'pre-wrap' }}>
    {p.replace(/^#{1,6}\s+/gm, '').split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
      part.startsWith('**') && part.endsWith('**') ? <strong key={j}>{part.slice(2, -2)}</strong> : part)}
  </p>)}</div>
}

const labels = { beat: 'Au-dessus du consensus', miss: 'Sous le consensus', inline: 'Conforme au consensus' }
export default function Results({ symbol }) {
  const [opened, setOpened] = useState(false)
  const [period, setPeriod] = useState('quarter')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [summaryError, setSummaryError] = useState('')
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  useEffect(() => {
    if (!opened) return
    let alive = true
    setData(null); setError(''); setSummaryError('')
    api.request(`/results/${encodeURIComponent(symbol)}?period=${period}`)
      .then(d => alive && setData(d)).catch(e => alive && setError(e.message))
    return () => { alive = false }
  }, [symbol, period, opened, version])
  async function summarize(refresh = false) {
    setBusy(true); setSummaryError('')
    try {
      const summary = await api.request(`/results/${encodeURIComponent(symbol)}/summary?period=${period}&refresh=${refresh}`, { method: 'POST' })
      setData(d => ({ ...d, summary }))
    } catch (e) { setSummaryError(e.message) } finally { setBusy(false) }
  }
  return <section>
    <div className="head-row"><h2>Résultats financiers</h2>{opened && <CurrencyToggle />}</div>
    {!opened ? <button className="btn" onClick={() => setOpened(true)}>Afficher les résultats</button> : <>
      <div className="seg" aria-label="Période des résultats">
        {[['quarter', 'Trimestres'], ['annual', 'Années']].map(([value, label]) => <button key={value} disabled={busy} className={period === value ? 'active' : ''} aria-pressed={period === value} onClick={() => setPeriod(value)}>{label}</button>)}
      </div>
      {error && <div className="banner error" role="alert">{error}<button className="chip" disabled={busy} onClick={() => setVersion(v => v + 1)}>Réessayer</button></div>}
      {!data && !error && <p className="muted">Chargement des résultats…</p>}
      {data && <>
        {data.stale && <p className="banner">Résultats en cache périmés : le fournisseur est indisponible.</p>}
        <p className="muted">Source : {data.source}. Montants abrégés en k, M et Md ; montant complet au survol. Conversion euro/dollar au taux actuel si disponible, sinon devise publiée. Les variations restent calculées dans la devise publiée, par rapport {period === 'annual' ? 'à l’année précédente' : 'au trimestre précédent (saisonnalité possible)'}. Pour une base négative, le pourcentage utilise sa valeur absolue.</p>
        {data.source === 'Alpha Vantage' && data.rows.length > 0 && <p className="muted">Le bénéfice par action n’est pas fourni dans ces comptes. Le chiffre d’affaires et le résultat net peuvent suffire au résumé.</p>}
        {!data.rows.length && <div className="card pad">
          <p>Aucun compte {period === 'annual' ? 'annuel' : 'trimestriel'} disponible pour ce titre auprès des sources actuelles.</p>
          {data.alternative_period && <button className="btn" onClick={() => setPeriod(data.alternative_period)}>
            Afficher les comptes {data.alternative_period === 'annual' ? 'annuels' : 'trimestriels'} disponibles
          </button>}
        </div>}
        {data.rows[0] && <Publication key={period + data.rows[0].date} row={data.rows[0]} />}
        {data.rows.length > 1 && <details key={period}>
          <summary>Voir les {data.rows.length - 1} {period === 'annual' ? 'années précédentes' : 'trimestres précédents'}</summary>
          {data.rows.slice(1).map(r => <Publication key={r.date} row={r} />)}
        </details>}
        <h2>Résultats face au consensus</h2>
        <p className="muted">Dates d’annonce, distinctes des fins de période ci-dessus. Montants tels que publiés par FMP, sans conversion ; la devise n’est pas fournie par cet endpoint. Les bénéfices ajustés du consensus peuvent différer des comptes.</p>
        {!data.earnings.length && <p className="muted">{data.consensus_warning || 'Consensus indisponible.'} Cela n’empêche pas le résumé des comptes publiés.</p>}
        {data.consensus_stale && <p className="muted">Comparaisons aux estimations en cache périmé.</p>}
        {data.earnings.map((e, i) => <div className="card pad portfolio-item" key={e.date + i}>
          <strong>Annonce du {e.date}</strong>
          {[['eps', 'Bénéfice par action'], ['revenue', 'Chiffre d’affaires']].map(([key, label]) => <p key={key}>{label} : {compactMoney(e[key + 'Actual'])} · attendu {compactMoney(e[key + 'Estimated'])}<br /><small className={trend(e[key + 'Surprise'])}>{labels[e[key + 'Result']] || 'Comparaison indisponible'} · {signedPct(e[key + 'Surprise'])}</small></p>)}
        </div>)}
        <h2>Lecture IA des résultats</h2>
        {summaryError && <p className="banner error" role="alert">{summaryError}</p>}
        {data.summary ? <div className="card pad">
          <p className="muted">{data.summary.model} · publication du {data.summary.publication}, comparée à celle du {data.summary.previous}. Généré le {new Date(data.summary.generated_at * 1000).toLocaleString('fr-FR')}.</p>
          {data.summary.data_changed && <p className="banner">Les chiffres ont été révisés depuis ce résumé. Le texte conservé n’a pas été régénéré.</p>}
          {data.summary.legacy_prompt && <p className="muted">Résumé créé avec les anciennes consignes. Tu peux le refaire avec une comparaison plus précise.</p>}
          <SummaryText text={data.summary.text} />
          <p className="muted">Le résumé conserve la devise des comptes publiés ; il ne suit pas la conversion d’affichage.</p>
          <button className="btn" disabled={busy || data.stale} onClick={() => summarize(true)}>{busy ? 'Analyse en cours…' : 'Refaire le résumé IA'}</button>
          <p className="muted">Un nouvel appel Gemini sera compté. Le texte existant est conservé si l’essai échoue.</p>
          <p className="muted">Lecture automatique à vérifier avec les chiffres publiés. Ce texte ne constitue pas une recommandation d’investissement.</p>
        </div> : <>
          <p className="muted">Analyse des deux dernières publications au clic uniquement. Seuls les chiffres publics sont transmis à Gemini, jamais ton portefeuille. Le texte est ensuite conservé.</p>
          {data.summary_unavailable && <p className="muted">{data.summary_unavailable}</p>}
          <button className="btn primary" disabled={busy || data.stale || data.rows.length < 2 || !!data.summary_unavailable} onClick={() => summarize()}>{busy ? 'Analyse en cours…' : summaryError ? 'Réessayer le résumé IA' : 'Générer le résumé IA'}</button>
        </>}
      </>}
    </>}
  </section>
}
