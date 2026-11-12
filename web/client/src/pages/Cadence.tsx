import { Link } from 'react-router-dom'
import { fmtDate, type Json } from '../api'
import { Empty, Loading, Page, Tile, useApi } from '../ui'

export default function Cadence() {
  const { data, error, loading } = useApi('/api/outreach/cadence')
  return (
    <Page title="Cadence" sub="Warm and hot leads by follow-up step">
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="tiles">
            <Tile label="Not yet contacted" value={data.pending} />
            <Tile label="Contacted" value={data.contacted} />
            {data.byStep.map((s: Json) => <Tile key={s.step} label={`Follow-up step ${s.step}`} value={s.n} />)}
          </div>
          <div className="card">
            <h2>Positive responses</h2>
            {data.responses.length ? (
              <table><thead><tr><th>Company</th><th>Contact</th><th>Product</th><th>Response</th><th className="num">Score</th><th>Last contact</th></tr></thead>
                <tbody>{data.responses.map((r: Json) => (
                  <tr key={r.id}><td><Link to={`/leads/${r.id}`}>{r.companyName}</Link></td><td>{r.fullName ?? '—'}</td><td>{r.targetProduct}</td>
                    <td>{r.responseStatus}</td><td className="num">{r.score}</td><td>{fmtDate(r.lastContactedAt)}</td></tr>))}</tbody></table>
            ) : <Empty>No positive responses yet.</Empty>}
          </div>
        </>
      )}
    </Page>
  )
}
