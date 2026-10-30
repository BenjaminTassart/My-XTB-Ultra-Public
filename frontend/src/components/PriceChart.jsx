import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { num, signedPct } from '../format.js'
import { rsi, sma } from '../indicators.js'

const RANGES = [
  { id: '1M', days: 22 }, { id: '3M', days: 63 }, { id: '6M', days: 126 },
  { id: '1A', days: 252 }, { id: '5A', days: Infinity },
]
const W = 600, PH = 240, RH = 84, L = 6, R = 54, T = 10, B = 22
const COLORS = { sma50: '#e0b45a', sma200: '#7aa7e8' }

const fmtDate = (d, long) =>
  new Date(d + 'T00:00:00').toLocaleDateString('fr-FR',
    long ? { day: '2-digit', month: 'short', year: 'numeric' } : { day: '2-digit', month: 'short', year: '2-digit' })

function path(rows, x, y, key) {
  let d = ''
  rows.forEach((r, i) => {
    if (r[key] == null) return
    d += (d ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(r[key]).toFixed(1)
  })
  return d
}

export default function PriceChart({ symbol, factor }) {
  const [hist, setHist] = useState(null)
  const [error, setError] = useState(null)
  const [range, setRange] = useState('3M')
  const [candles, setCandles] = useState(false)
  const [showSma, setShowSma] = useState(false)
  const [showRsi, setShowRsi] = useState(false)
  const [hover, setHover] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    let alive = true
    setHist(null); setError(null); setHover(null)
    api.history(symbol).then((d) => alive && setHist(d)).catch((e) => alive && setError(e))
    return () => { alive = false }
  }, [symbol])

  const rows = useMemo(() => {
    if (!hist || hist.points.length < 2) return null
    const pts = hist.points
    const closes = pts.map((p) => p[4])
    const s50 = sma(closes, 50), s200 = sma(closes, 200), r = rsi(closes, 14)
    const days = RANGES.find((x) => x.id === range).days
    const start = Math.max(0, pts.length - (Number.isFinite(days) ? days : pts.length))
    const group = days > 252 ? 5 : 1 // sur 5 ans : une bougie par semaine
    const f = (v) => (v == null ? null : v * factor)
    const out = []
    for (let i = start; i < pts.length; i += group) {
      const end = Math.min(i + group, pts.length) - 1
      let hi = -Infinity, lo = Infinity
      for (let j = i; j <= end; j++) { hi = Math.max(hi, pts[j][2]); lo = Math.min(lo, pts[j][3]) }
      out.push({ date: pts[end][0], o: f(pts[i][1]), h: f(hi), l: f(lo), c: f(pts[end][4]),
                 s50: f(s50[end]), s200: f(s200[end]), rsi: r[end] })
    }
    return out
  }, [hist, range, factor])

  if (error) return <div className="banner">{error.message}</div>
  if (!hist) return <div className="spinner">Chargement du graphique…</div>
  if (!rows || rows.length < 2) return <div className="banner">Historique insuffisant pour ce titre.</div>

  const n = rows.length
  const step = (W - L - R) / n
  const x = (i) => L + (i + 0.5) * step
  const vals = []
  rows.forEach((r) => {
    if (candles) vals.push(r.h, r.l); else vals.push(r.c)
    if (showSma) { if (r.s50 != null) vals.push(r.s50); if (r.s200 != null) vals.push(r.s200) }
  })
  let min = Math.min(...vals), max = Math.max(...vals)
  const pad = (max - min || 1) * 0.06
  min -= pad; max += pad
  const y = (v) => T + (1 - (v - min) / (max - min)) * (PH - T - B)
  const y2 = (v) => 4 + (1 - v / 100) * (RH - 8)

  const first = rows[0].c, last = rows[n - 1].c
  const trendColor = last >= first ? 'var(--up)' : 'var(--down)'
  const line = path(rows, x, y, 'c')
  const area = `${line}L${x(n - 1).toFixed(1)},${PH - B}L${x(0).toFixed(1)},${PH - B}Z`
  const ticks = [0, 1, 2, 3].map((k) => min + ((max - min) * k) / 3)
  const labelIdx = [0, Math.floor((n - 1) / 2), n - 1]
  const longRange = range === '1A' || range === '5A'

  function onMove(e) {
    const box = ref.current.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    setHover(Math.max(0, Math.min(n - 1, Math.round((px - L) / step - 0.5))))
  }

  const h = hover != null ? rows[hover] : null

  return (
    <div>
      {hist.source === 'twelvedata' && <p className="muted">Historique fourni par Twelve Data · séances quotidiennes disponibles, jusqu’à 5 ans.</p>}
      <div className="chart-bar">
        <div className="seg" role="group" aria-label="Période">
          {RANGES.map((r) => (
            <button key={r.id} className={range === r.id ? 'active' : ''} aria-pressed={range === r.id}
                    onClick={() => { setRange(r.id); setHover(null) }}>{r.id}</button>
          ))}
        </div>
      </div>

      <div className="chart-info">
        {h ? (
          <>
            <span className="muted">{fmtDate(h.date, true)}</span>{' '}
            {candles
              ? <span>O {num(h.o)} · H {num(h.h)} · B {num(h.l)} · C <b>{num(h.c)}</b></span>
              : <b>{num(h.c)}</b>}
            {showRsi && h.rsi != null && <span className="muted"> · RSI {num(h.rsi, 0)}</span>}
          </>
        ) : (
          <>
            <b>{num(last)}</b>{' '}
            <span className={last >= first ? 'up' : 'down'}>{signedPct(((last / first) - 1) * 100)}</span>
            <span className="muted"> sur la période</span>
          </>
        )}
      </div>

      <svg ref={ref} viewBox={`0 0 ${W} ${PH}`} className="chart" role="img"
           aria-label={`Graphique du cours de ${symbol}`} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid-line" />
            <text x={W - R + 6} y={y(t) + 4} className="axis">{num(t)}</text>
          </g>
        ))}
        {labelIdx.map((i, k) => (
          <text key={k} x={x(i)} y={PH - 6} className="axis" textAnchor={k === 0 ? 'start' : k === 2 ? 'end' : 'middle'}>
            {fmtDate(rows[i].date, longRange)}
          </text>
        ))}
        {!candles && <path d={area} fill={trendColor} opacity="0.08" />}
        {!candles && <path d={line} fill="none" stroke={trendColor} strokeWidth="1.8" strokeLinejoin="round" />}
        {candles && rows.map((r, i) => {
          const up = r.c >= r.o
          const col = up ? 'var(--up)' : 'var(--down)'
          const bw = Math.max(1.2, step * 0.62)
          return (
            <g key={i}>
              <line x1={x(i)} x2={x(i)} y1={y(r.h)} y2={y(r.l)} stroke={col} strokeWidth="1" />
              <rect x={x(i) - bw / 2} y={Math.min(y(r.o), y(r.c))} width={bw}
                    height={Math.max(1, Math.abs(y(r.o) - y(r.c)))} fill={col} />
            </g>
          )
        })}
        {showSma && <path d={path(rows, x, y, 's50')} fill="none" stroke={COLORS.sma50} strokeWidth="1.3" />}
        {showSma && <path d={path(rows, x, y, 's200')} fill="none" stroke={COLORS.sma200} strokeWidth="1.3" />}
        {h && <line x1={x(hover)} x2={x(hover)} y1={T} y2={PH - B} className="cross" />}
      </svg>

      {showRsi && (
        <svg viewBox={`0 0 ${W} ${RH}`} className="chart rsi" role="img" aria-label="RSI 14 périodes"
             onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {[30, 70].map((v) => (
            <g key={v}>
              <line x1={L} x2={W - R} y1={y2(v)} y2={y2(v)} className="grid-line dashed" />
              <text x={W - R + 6} y={y2(v) + 4} className="axis">{v}</text>
            </g>
          ))}
          <path d={path(rows, x, y2, 'rsi')} fill="none" stroke="var(--text)" strokeWidth="1.3" />
          {h && <line x1={x(hover)} x2={x(hover)} y1={4} y2={RH - 4} className="cross" />}
        </svg>
      )}

      <div className="chips" style={{ marginTop: 10 }}>
        <button className="chip" aria-pressed={candles} onClick={() => setCandles(!candles)}>Chandeliers</button>
        <button className="chip" aria-pressed={showSma} onClick={() => setShowSma(!showSma)}>
          Moyennes mobiles <span style={{ color: COLORS.sma50 }}>50</span> / <span style={{ color: COLORS.sma200 }}>200</span>
        </button>
        <button className="chip" aria-pressed={showRsi} onClick={() => setShowRsi(!showRsi)}>RSI 14</button>
      </div>
      {hist.stale && <p className="muted" style={{ fontSize: 12 }}>Historique en cache (fournisseur momentanément indisponible).</p>}
      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
        Cours journaliers (pas d'intraday en gratuit){factor !== 1 ? ', convertis au taux du jour' : ''}.
        {range === '5A' ? ' Une bougie par semaine sur 5 ans.' : ''}
      </p>
    </div>
  )
}
