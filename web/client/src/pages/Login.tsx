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
      <form className="card stack" onSubmit={submit}>
        <div><h1>Shiplystic <span style={{ color: 'var(--accent)' }}>Leads</span></h1><div className="muted">Sign in to your calling workspace</div></div>
        <label className="field">Username<input autoFocus autoComplete="username" value={u} onChange={e => setU(e.target.value)} required /></label>
        <label className="field">Password<input type="password" autoComplete="current-password" value={p} onChange={e => setP(e.target.value)} required /></label>
        {err && <div className="error-text">{err}</div>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
