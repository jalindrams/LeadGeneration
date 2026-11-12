import { useState } from 'react'
import { api, fmtDate, type Json } from '../api'
import { Loading, Page, StatusBadge, useApi } from '../ui'

export default function Users() {
  const { data, error, loading, reload } = useApi('/api/admin/users')
  const [form, setForm] = useState({ username: '', fullName: '', password: '', role: 'sales_rep' })
  const [msg, setMsg] = useState<string | null>(null)
  const create = async () => {
    setMsg(null)
    try { await api.post('/api/admin/users', form); setMsg(`Created ${form.username}.`); setForm({ username: '', fullName: '', password: '', role: 'sales_rep' }); reload() }
    catch (e) { setMsg((e as Error).message) }
  }
  const toggle = async (id: number) => { try { await api.post(`/api/admin/users/${id}/toggle`); reload() } catch (e) { setMsg((e as Error).message) } }
  const reset = async (u: Json) => {
    const pw = window.prompt(`New password for ${u.username} (at least 8 characters)`)
    if (!pw) return
    try { await api.post(`/api/admin/users/${u.id}/password`, { password: pw }); setMsg(`Password changed for ${u.username}.`) } catch (e) { setMsg((e as Error).message) }
  }
  return (
    <Page title="Users">
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Add a user</h2>
        <div className="filters">
          <label className="field">Username<input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
          <label className="field">Full name<input value={form.fullName} onChange={e => setForm({ ...form, fullName: e.target.value })} /></label>
          <label className="field">Password<input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
          <label className="field">Role<select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="sales_rep">Sales rep</option><option value="admin">Admin</option></select></label>
          <button className="primary" disabled={!form.username || !form.fullName || form.password.length < 8} onClick={create}>Add user</button>
        </div>
        {msg && <div className="muted">{msg}</div>}
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="card table-wrap"><table>
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th className="num">Leads assigned</th><th>Status</th><th>Created</th><th></th></tr></thead>
          <tbody>{data.map((u: Json) => (
            <tr key={u.id}><td>{u.fullName}</td><td className="mono">{u.username}</td><td>{u.role}</td><td className="num">{u.assigned}</td>
              <td><StatusBadge ok={u.isActive !== false}>{u.isActive !== false ? 'Active' : 'Inactive'}</StatusBadge></td><td>{fmtDate(u.createdAt)}</td>
              <td className="row"><button onClick={() => toggle(u.id)}>{u.isActive !== false ? 'Deactivate' : 'Activate'}</button><button onClick={() => reset(u)}>Reset password</button></td></tr>))}</tbody>
        </table></div>
      )}
    </Page>
  )
}
