import { useState } from 'react'
import { api, fmtDate, pct, type Json } from '../api'
import { Bars, Loading, Meter, Page, Tile, useApi } from '../ui'

/** Always 14 daily slots ending today, so one day of history does not fill the chart. */
function last14(history: Json[], target: number) {
  const byDay = new Map(history.map((h: Json) => [String(h.date).slice(0, 10), h]))
  return Array.from({ length: 14 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - 13 + i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const h = byDay.get(key)
    const label = fmtDate(key)
    return { key: label, value: h?.delivered ?? 0, tip: h ? `${label}: ${h.delivered} of ${h.target}` : `${label}: no batch (target ${target})` }
  })
}

export default function Target() {
  const { data, error, loading, reload } = useApi('/api/pipeline/target')
  const { data: funnel } = useApi('/api/pipeline/funnel')
  const [msg, setMsg] = useState<string | null>(null)
  const run = async (name: string, options?: Record<string, string>) => {
    setMsg(null)
    try { const j = await api.post('/api/admin/jobs', { name, options }); setMsg(`Started ${j.name}. Follow it on Workers & scrapers.`) }
    catch (e) { setMsg((e as Error).message) }
  }
  return (
    <Page title="Daily target" sub="50 call-ready Shiplystic leads every day"
          actions={<><button onClick={() => run('pipeline_process')}>Process backlog</button>
                     <button className="primary" onClick={() => run('pipeline_batch')}>Build today's batch</button>
                     <button onClick={reload}>Refresh</button></>}>
      {msg && <div className="notice" style={{ marginBottom: 12 }}>{msg}</div>}
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="card" style={{ marginBottom: 14 }}>
            <Meter label={`Delivered today (${fmtDate(data.today.date)})`} value={data.today.delivered} max={data.today.target} />
            {data.today.shortfall && <div className="small" style={{ marginTop: 6 }}><span className="badge warn">Short</span> {data.today.shortfall}</div>}
          </div>
          <div className="tiles">
            <Tile label="Ready to deliver" value={data.readyToDeliver} sub={`≈ ${data.daysAvailable} days of supply`} />
            <Tile label="Accepted today" value={data.acceptedToday} />
            <Tile label="Still in pipeline" value={data.inPipeline} sub="discovered, qualified or resolved" />
            <Tile label="Delivered so far" value={data.states?.delivered ?? 0} />
          </div>
          <div className="card" style={{ marginBottom: 14 }}>
            <h2>Delivered per day (target {data.today.target})</h2>
            <Bars label="Leads delivered per day" target={data.today.target} items={last14(data.history, data.today.target)} />
            <div className="small muted" style={{ marginTop: 4 }}>Lighter bars are days below target.</div>
          </div>
        </>
      )}
      {funnel && (
        <div className="card">
          <h2>Sources: funnel and call quality</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Source</th><th className="num">Found</th><th className="num">In progress</th><th className="num">Rejected</th><th className="num">Accepted</th>
              <th className="num">Delivered</th><th className="num">Called</th><th className="num">Reached</th><th className="num">Wrong no.</th><th className="num">Positive</th><th>Top reject reasons</th></tr></thead>
            <tbody>{funnel.map((s: Json) => (
              <tr key={s.source}><td>{s.source}</td><td className="num">{s.total}</td><td className="num">{s.discovered}</td><td className="num">{s.rejected}</td>
                <td className="num">{s.accepted}</td><td className="num">{s.delivered}</td><td className="num">{s.called}</td>
                <td className="num">{pct(s.reachRate)}</td><td className="num">{pct(s.wrongRate)}</td><td className="num">{pct(s.positiveRate)}</td>
                <td className="small">{s.rejectReasons.slice(0, 3).map((r: Json) => `${r.reason} ${r.n}`).join(' · ')}</td></tr>))}</tbody>
          </table></div>
          <div className="small muted" style={{ marginTop: 6 }}>Call rates use each lead's latest outcome. Sources are auto-throttled after 30 calls (weekly ranking).</div>
        </div>
      )}
    </Page>
  )
}
