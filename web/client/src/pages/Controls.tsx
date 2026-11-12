import { useState } from 'react'
import { api, fmtTime, type Json } from '../api'
import { Loading, Meter, Page, Tile, useApi } from '../ui'

export default function Controls() {
  const [search, setSearch] = useState('')
  const { data: sup, reload } = useApi(`/api/pipeline/suppression?search=${encodeURIComponent(search)}`)
  const { data: spend, error, loading } = useApi('/api/pipeline/spend')
  const [kind, setKind] = useState('phone')
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('do_not_call')
  const [msg, setMsg] = useState<string | null>(null)
  const add = async () => {
    setMsg(null)
    try { const r = await api.post('/api/pipeline/suppression', { kind, value, reason }); setMsg(r.existed ? `${r.value} was already blocked.` : `Blocked ${r.value}.`); setValue(''); reload() }
    catch (e) { setMsg((e as Error).message) }
  }
  const remove = async (id: number) => { await api.del(`/api/pipeline/suppression/${id}`); reload() }
  const setting = (key: string) => spend?.settings?.find((s: Json) => s.key === key)
  const cap = (key: string) => Number(setting(key)?.value || 0)
  const total = cap('PAID_TOTAL_CAP_INR')
  return (
    <Page title="Suppression & spend" sub="Numbers we never call again, and the paid-source budget">
      <div className="grid g2">
        <div className="card stack">
          <h2>Paid sources this month</h2>
          <Loading error={error} loading={loading && !spend} />
          {spend && (
            <>
              {total > 0
                ? <Meter label={`Total spend ${spend.month} (₹)`} value={Math.round(spend.totalSpent)} max={total} />
                : <div className="notice"><span className="badge ok">Off</span> Paid sources are switched off (total cap ₹0). Set caps and keys in Settings to enable them.</div>}
              <div className="tiles">
                {['SERPER', 'STORELEADS', 'EASYLEADZ', 'GOOGLE_PLACES'].map(p => {
                  const row = spend.rows.find((r: Json) => r.provider.toUpperCase() === p)
                  return <Tile key={p} label={p.replace('_', ' ').toLowerCase()} value={`₹${Math.round(row?.costInr ?? 0)}`} sub={`cap ₹${cap(`PAID_${p}_CAP_INR`)}`} />
                })}
              </div>
            </>
          )}
        </div>
        <div className="card stack">
          <h2>Block a number, domain or email</h2>
          <div className="filters">
            <label className="field">Type<select value={kind} onChange={e => setKind(e.target.value)}><option>phone</option><option>domain</option><option>email</option></select></label>
            <label className="field">Value<input value={value} onChange={e => setValue(e.target.value)} placeholder="98123 45678" /></label>
            <label className="field">Reason<select value={reason} onChange={e => setReason(e.target.value)}>
              {['do_not_call', 'wrong_number', 'opt_out', 'competitor', 'manual'].map(r => <option key={r}>{r}</option>)}</select></label>
            <button className="primary" disabled={!value} onClick={add}>Block</button>
          </div>
          {msg && <div className="muted">{msg}</div>}
        </div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="spread"><h2>Suppression list</h2><input placeholder="Search" value={search} onChange={e => setSearch(e.target.value)} /></div>
        {sup?.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Value</th><th>Type</th><th>Reason</th><th>Added</th><th>By</th><th></th></tr></thead>
            <tbody>{sup.map((s: Json) => (
              <tr key={s.id}><td className="mono">{s.value}</td><td>{s.kind}</td><td>{s.reason}</td><td>{fmtTime(s.addedAt)}</td><td>{s.addedBy}</td>
                <td><button className="danger" onClick={() => remove(s.id)}>Unblock</button></td></tr>))}</tbody>
          </table></div>
        ) : <div className="muted">Nothing blocked yet.</div>}
      </div>
    </Page>
  )
}
