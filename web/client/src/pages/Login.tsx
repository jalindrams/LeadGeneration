import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'

export default function Login() {
  const { login } = useAuth()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try { await login(u, p) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <section className="login-hero">
        <div className="logo" aria-hidden="true">S</div>
        <h2>Call the right stores, report in seconds.</h2>
        <p>Your daily list of ecommerce stores, one lead at a time, with the opener ready and the outcome one tap away.</p>
        <ul><li>Fresh leads every morning</li><li>One-tap outcomes and follow-ups</li><li>Works on your phone</li></ul>
      </section>
      <div className="login-pane">
        <form className="card stack" onSubmit={submit}>
          <div><h1>Welcome back</h1><div className="muted">Sign in to your calling workspace</div></div>
          <label className="field">Username<input autoFocus autoComplete="username" value={u} onChange={e => setU(e.target.value)} required /></label>
          <label className="field">Password<input type="password" autoComplete="current-password" value={p} onChange={e => setP(e.target.value)} required /></label>
          {err && <div className="notice error error-text" role="alert">{err}</div>}
          <button className="primary" style={{ justifyContent: 'center' }} disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </div>
    </div>
  )
}
