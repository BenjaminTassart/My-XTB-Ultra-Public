import React, { useState } from 'react'
import { setCode } from '../api.js'

export default function LoginGate({ onDone, wrong }) {
  const [value, setValue] = useState('')

  function submit(e) {
    e.preventDefault()
    setCode(value.trim())
    onDone()
  }

  return (
    <div className="center">
      <form className="login" onSubmit={submit}>
        <h1>My XTB Ultra</h1>
        <p className="muted">Saisis ton code d'accès.</p>
        <input className="input" type="password" autoFocus value={value} placeholder="Code d'accès"
               onChange={(e) => setValue(e.target.value)} />
        {wrong && <p className="down">Code invalide, réessaie.</p>}
        <p><button className="btn primary" disabled={!value.trim()}>Entrer</button></p>
      </form>
    </div>
  )
}
