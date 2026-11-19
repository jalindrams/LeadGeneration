import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtTime, type Json } from '../api'
import { Empty, Page, Tile, useApi } from '../ui'

export default function Outreach() {
  const [status, setStatus] = useState('queued')
  const { data, reload } = useApi(`/api/outreach/log?status=${status}`)
  const { data: stats } = useApi('/api/outreach/stats')
  const [msg, setMsg] = useState<string | null>(null)
  const mark = async (id: number, s: string) => { await api.post(`/api/outreach/log/${id}/status`, { status: s }); reload() }
  const dryRun = async () => {
    try { await api.post('/api/outreach/run', { product: 'all', tier: 'hot', limit: 50, dryRun: true }); setMsg('Dry run started (nothing is sent). See its log on Workers & scrapers.') }
    catch (e) { setMsg((e as Error).message) }
  }
  const count = (s: string) => (stats ?? []).filter((r: Json) => r.status === s).reduce((a: number, r: Json) => a + r.n, 0)
  return (
    <Page title="Outreach" sub="WhatsApp intros are queued for a person to send from the company phone; this app never sends them"
          actions={<button onClick={dryRun}>Preview cadence (dry run)</button>}>
      {msg && <div className="notice" style={{ marginBottom: 12 }}>{msg}</div>}
      <div className="tiles">
        <Tile label="Queued" value={count('queued')} /><Tile label="Sent (30 days)" value={count('sent')} />
        <Tile label="Responded" value={count('responded')} /><Tile label="Failed / skipped" value={count('failed') + count('skipped')} />
      </div>
      <div className="tabs">{['queued', 'sent', 'responded', 'skipped', 'failed'].map(s => <button key={s} className={status === s ? 'on' : ''} onClick={() => setStatus(s)}>{s}</button>)}</div>
      {data?.length ? (
        <div className="card table-wrap"><table>
          <thead><tr><th>Lead</th><th>Phone</th><th>Message</th><th>Created</th><th></th></tr></thead>
          <tbody>{data.map((o: Json) => (
            <tr key={o.id}><td><Link to={`/leads/${o.leadId}`}>{o.companyName}</Link><div className="small muted">{o.channel} · {o.templateKey}</div></td>
              <td className="mono">{o.phone}</td><td className="small" style={{ maxWidth: 420 }}>{o.messagePreview}</td><td>{fmtTime(o.createdAt)}</td>
              <td className="row">{status === 'queued' && <>
                <a className="btn" target="_blank" rel="noreferrer noopener" href={`https://wa.me/91${(o.phone || '').slice(-10)}?text=${encodeURIComponent(o.messagePreview || '')}`}>Open WhatsApp</a>
                <button className="primary" onClick={() => mark(o.id, 'sent')}>Mark sent</button><button onClick={() => mark(o.id, 'skipped')}>Skip</button></>}
                {status === 'sent' && <button onClick={() => mark(o.id, 'responded')}>Mark responded</button>}</td></tr>))}</tbody>
        </table></div>
      ) : <Empty>Nothing {status}.</Empty>}
    </Page>
  )
}
