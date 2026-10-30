import React from 'react'
import { useDisplayCurrency } from '../currency.js'

export default function CurrencyToggle() {
  const [current, set] = useDisplayCurrency()
  return (
    <div className="seg" role="group" aria-label="Devise d'affichage">
      {[['EUR', '€ Euro'], ['USD', '$ Dollar']].map(([code, label]) => (
        <button key={code} className={current === code ? 'active' : ''} aria-pressed={current === code}
                onClick={() => set(code)}>{label}</button>
      ))}
    </div>
  )
}
