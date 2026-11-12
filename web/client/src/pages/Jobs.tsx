import { useEffect, useState } from 'react'
import { api, fmtTime, type Json } from '../api'
import { Page, useApi } from '../ui'

const SCRAPER_SOURCES = ['indiamart', 'google_maps', 'tradeindia', 'nabl', 'aipma', 'iba', 'oem_dealers']
const PRODUCTS = ['mes', 'dms', 'tms', 'courier', 'calibration', 'ecom']

export default function Jobs() {
  const { data, reload } = useApi('/api/admin/jobs')
  const { data: scrapes } = useApi('/api/admin/scrape-jobs')
  const [log, setLog] = useState<{ id: string; text: string } | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [scraper, setScraper] = useState({ source: 'indiamart', product: 'mes' })

  useEffect(() => {
    if (!data?.some((j: Json) => j.status === 'running')) return
    const t = setInterval(reload, 4000)
    return () => clearInterval(t)
  }, [data, reload])

  const start = async (name: string, options?: Record<string, string>) => {
    setMsg(null)
    try { await api.post('/api/admin/jobs', { name, options }); reload() } catch (e) { setMsg((e as Error).message) }
  }
  const showLog = async (id: string) => setLog({ id, text: await api.get(`/api/admin/jobs/${id}/log`) })
  const stop = async (id: string) => { await api.post(`/api/admin/jobs/${id}/stop`); reload() }

  return (
    <Page title="Workers & scrapers" sub="Start Python worker jobs on this server and watch their output">
      <div className="grid g2">
        <div className="card stack">
          <h2>Shiplystic pipeline</h2>
          <div className="row">
            <button className="primary" onClick={() => start('pipeline_daily')}>Full daily cycle</button>
            <button onClick={() => start('pipeline_process')}>Process backlog</button>
            <button onClick={() => start('pipeline_batch')}>Build batch</button>
            <button onClick={() => start('pipeline_rank')}>Rank sources</button>
            <button onClick={() => start('rescore')}>Rescore leads</button>
          </div>
          <p className="small muted" style={{ margin: 0 }}>The always-on schedule runs from <span className="mono">run_pipeline_worker.bat</span>; these buttons run a step now.</p>
        </div>
        <div className="card stack">
          <h2>Product scrapers (MES, DMS, TMS…)</h2>
          <div className="filters">
            <label className="field">Source<select value={scraper.source} onChange={e => setScraper({ ...scraper, source: e.target.value })}>{SCRAPER_SOURCES.map(s => <option key={s}>{s}</option>)}</select></label>
            <label className="field">Product<select value={scraper.product} onChange={e => setScraper({ ...scraper, product: e.target.value })}>{PRODUCTS.map(s => <option key={s}>{s}</option>)}</select></label>
            <button onClick={() => start('scraper', { ...scraper, yes: 'true' })}>Start scraper</button>
          </div>
        </div>
      </div>
      {msg && <div className="notice error" style={{ marginTop: 12 }}>{msg}</div>}
      <div className="card" style={{ marginTop: 14 }}>
        <h2>Jobs started from this app</h2>
        {data?.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Started</th><th>Job</th><th>Command</th><th>Status</th><th></th></tr></thead>
            <tbody>{data.map((j: Json) => (
              <tr key={j.id}><td>{fmtTime(j.startedAt)}</td><td>{j.name}</td><td className="mono small">{j.args.join(' ')}</td>
                <td><span className={`badge ${j.status === 'ok' ? 'ok' : j.status === 'running' ? 'warn' : 'fail'}`}>{j.status}</span></td>
                <td className="row"><button onClick={() => showLog(j.id)}>Log</button>{j.status === 'running' && <button className="danger" onClick={() => stop(j.id)}>Stop</button>}</td></tr>))}</tbody>
          </table></div>
        ) : <div className="muted">No jobs started since the server started.</div>}
        {log && <><div className="spread" style={{ marginTop: 10 }}><b>{log.id}</b><button onClick={() => showLog(log.id)}>Refresh log</button></div><pre className="log">{log.text || '(no output yet)'}</pre></>}
      </div>
      {scrapes?.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h2>Scraper history</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Started</th><th>Source</th><th>Query</th><th>City</th><th>Status</th><th className="num">Found</th><th className="num">Stored</th></tr></thead>
            <tbody>{scrapes.map((s: Json) => (
              <tr key={s.id}><td>{fmtTime(s.startedAt)}</td><td>{s.source}</td><td>{s.searchQuery}</td><td>{s.city}</td><td>{s.status}</td>
                <td className="num">{s.recordsFound}</td><td className="num">{s.recordsStored}</td></tr>))}</tbody>
          </table></div>
        </div>
      )}
    </Page>
  )
}
