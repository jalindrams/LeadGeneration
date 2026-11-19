import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtTime, qs, type Json } from '../api'
import { Loading, Page, Pager, TierBadge, useApi } from '../ui'

const SOURCES = ['shopify_app_reviews', 'tranco_in', 'tranco_com', 'new_domains', 'commoncrawl', 'amazon_sellers', 'serper_search', 'storeleads']

export default function Pipeline() {
  const [f, setF] = useState({ state: '', tier: '', source: '', search: '' })
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [src, setSrc] = useState('tranco_in')
  const { data, error, loading } = useApi(`/api/pipeline/stores${qs({ ...f, page })}`)
  const { data: runs, reload: reloadRuns } = useApi('/api/pipeline/runs')
  const { data: detail } = useApi(open ? `/api/pipeline/stores/${open}` : null)
  const set = (k: string) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setPage(1) }
  const discover = async () => {
    try { await api.post('/api/admin/jobs', { name: 'pipeline_discover', options: { source: src } }); setMsg(`Discovery started for ${src}.`); reloadRuns() }
    catch (e) { setMsg((e as Error).message) }
  }
  return (
    <Page title="Store pipeline" sub="Every store found, and why it was accepted or rejected"
          actions={<><select value={src} onChange={e => setSrc(e.target.value)}>{SOURCES.map(s => <option key={s}>{s}</option>)}</select>
                     <button className="primary" onClick={discover}>Run discovery</button></>}>
      {msg && <div className="notice" style={{ marginBottom: 12 }}>{msg}</div>}
      <div className="filters">
        <label className="field">Search<input value={f.search} onChange={set('search')} placeholder="domain or name" /></label>
        <label className="field">State<select value={f.state} onChange={set('state')}>
          {['', 'discovered', 'qualified', 'resolved', 'accepted', 'delivered', 'rejected'].map(s => <option key={s} value={s}>{s || 'Any'}</option>)}</select></label>
        <label className="field">Tier<select value={f.tier} onChange={set('tier')}>{['', 'A', 'B', 'C'].map(s => <option key={s} value={s}>{s || 'Any'}</option>)}</select></label>
        <label className="field">Source<select value={f.source} onChange={set('source')}>{['', ...SOURCES].map(s => <option key={s} value={s}>{s || 'Any'}</option>)}</select></label>
      </div>
      <Loading error={error} loading={loading && !data} />
      <div className="grid g2">
        {data && (
          <div className="card">
            <div className="table-wrap"><table>
              <thead><tr><th>Store</th><th>State</th><th>Tier</th><th className="num">Score</th><th className="num">Products</th><th>Ships with</th></tr></thead>
              <tbody>{data.stores.map((s: Json) => (
                <tr key={s.id} onClick={() => setOpen(s.id)} style={{ cursor: 'pointer' }}>
                  <td><b>{s.name || s.domain}</b><div className="small muted">{s.domain} · {s.source}</div></td>
                  <td>{s.state}{s.rejectReason && <div className="small muted">{s.rejectReason}</div>}</td>
                  <td><TierBadge tier={s.tier} /></td><td className="num">{s.score ?? '—'}</td><td className="num">{s.productCount ?? '—'}</td>
                  <td>{s.competitorTool ?? '—'}</td></tr>))}</tbody>
            </table></div>
            <Pager page={page} total={data.total} per={50} onPage={setPage} />
          </div>
        )}
        <div className="stack">
          {detail ? (
            <div className="card">
              <div className="spread"><h2>{detail.store.name || detail.store.domain}</h2><button onClick={() => setOpen(null)}>Close</button></div>
              <dl className="kv">
                <dt>Website</dt><dd><a href={`https://${detail.store.domain}`} target="_blank" rel="noreferrer noopener">{detail.store.domain}</a></dd>
                <dt>State</dt><dd>{detail.store.state} {detail.store.rejectReason && `(${detail.store.rejectReason})`}</dd>
                <dt>Platform</dt><dd>{detail.store.platform ?? '—'} · {detail.store.currency ?? '—'} · {detail.store.city ?? '—'}</dd>
                <dt>GSTIN</dt><dd className="mono">{detail.store.gstin ?? '—'}</dd>
                <dt>Source</dt><dd>{detail.store.source}<div className="small muted">{detail.store.sourceRef}</div></dd>
                {detail.store.sourceNote && <><dt>Note</dt><dd className="small">{detail.store.sourceNote}</dd></>}
                {detail.store.leadId && <><dt>Lead</dt><dd><Link to={`/leads/${detail.store.leadId}`}>Open lead</Link></dd></>}
              </dl>
              <h2 style={{ marginTop: 12 }}>Contacts</h2>
              {detail.contacts.length ? <table><tbody>{detail.contacts.map((c: Json) => (
                <tr key={c.id}><td className="mono">{c.phone ?? c.email ?? c.name}</td><td>{c.phoneType ?? c.role}</td>
                  <td className="small">{c.sourceUrl}</td></tr>))}</tbody></table> : <div className="muted">None found.</div>}
              <h2 style={{ marginTop: 12 }}>Signals</h2>
              {detail.signals.length ? <ul>{detail.signals.map((s: Json) => <li key={s.id}>{s.signalType}: {s.value}</li>)}</ul> : <div className="muted">None.</div>}
            </div>
          ) : <div className="card muted">Select a store to see its evidence.</div>}
          {runs && (
            <div className="card">
              <h2>Recent runs</h2>
              <div className="table-wrap"><table>
                <thead><tr><th>When</th><th>Source</th><th>Result</th><th className="num">New</th><th className="num">Accepted</th></tr></thead>
                <tbody>{runs.slice(0, 15).map((r: Json) => (
                  <tr key={r.id}><td>{fmtTime(r.startedAt)}</td><td>{r.source}/{r.stage}</td>
                    <td><span className={`badge ${r.status === 'ok' ? 'ok' : r.status === 'failed' ? 'fail' : 'warn'}`}>{r.status}</span>
                      {r.error && <div className="small muted">{r.error.slice(0, 90)}</div>}</td>
                    <td className="num">{r.discovered ?? 0}</td><td className="num">{r.accepted ?? 0}</td></tr>))}</tbody>
              </table></div>
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
