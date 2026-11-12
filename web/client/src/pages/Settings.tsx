import { useState } from 'react'
import { api, type Json } from '../api'
import { Loading, Page, StatusBadge, useApi } from '../ui'

export default function Settings() {
  const { data, error, loading, reload } = useApi('/api/settings')
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const save = async () => {
    setMsg(null)
    try { const r = await api.post('/api/settings', edits); setMsg(`Saved ${r.saved} setting(s). ${r.note}`); setEdits({}); reload() }
    catch (e) { setMsg((e as Error).message) }
  }
  const groups: Record<string, Json[]> = {}
  for (const f of data ?? []) (groups[f.group] ??= []).push(f)
  return (
    <Page title="Settings" sub="Stored in the project .env shared with the Python workers. Secret values are never shown."
          actions={<button className="primary" disabled={!Object.keys(edits).length} onClick={save}>Save changes</button>}>
      {msg && <div className="notice" style={{ marginBottom: 12 }}>{msg}</div>}
      <Loading error={error} loading={loading && !data} />
      <div className="grid g2">
        {Object.entries(groups).map(([g, fields]) => (
          <div className="card stack" key={g}>
            <h2>{g}</h2>
            {fields.map(f => (
              <label className="field" key={f.key}>
                <span className="spread">{f.label} <StatusBadge ok={f.isSet ? true : null}>{f.isSet ? 'set' : 'not set'}</StatusBadge></span>
                <input type={f.secret ? 'password' : 'text'} autoComplete="off"
                       placeholder={f.secret ? (f.isSet ? 'Leave blank to keep current value' : 'Not set') : ''}
                       value={edits[f.key] ?? (f.secret ? '' : f.value ?? '')}
                       onChange={e => setEdits({ ...edits, [f.key]: e.target.value })} />
                <span className="mono small muted">{f.key}</span>
              </label>
            ))}
          </div>
        ))}
      </div>
    </Page>
  )
}
