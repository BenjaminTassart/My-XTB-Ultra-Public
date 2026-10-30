import React from 'react'
import Icon from './Icon.jsx'

const ITEMS = [
  { id: 'home', label: 'Accueil', icon: 'home' },
  { id: 'search', label: 'Recherche', icon: 'search' },
  { id: 'portfolio', label: 'Portefeuille', icon: 'briefcase' },
  { id: 'settings', label: 'Paramètres', icon: 'settings' },
]

export default function Nav({ tab, onChange }) {
  return (
    <nav className="nav" aria-label="Navigation principale">
      <div className="nav-brand">My XTB Ultra</div>
      {ITEMS.map((it) => (
        <button key={it.id} className={'nav-item' + (tab === it.id ? ' active' : '')}
                onClick={() => onChange(it.id)} aria-current={tab === it.id ? 'page' : undefined}>
          <Icon name={it.icon} />
          <span>{it.label}</span>
        </button>
      ))}
    </nav>
  )
}
