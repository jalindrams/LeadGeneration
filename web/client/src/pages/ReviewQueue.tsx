import { Link } from 'react-router-dom'
import { api, fmtDate, type Json } from '../api'
import { Empty, Loading, Page, useApi } from '../ui'

export default function ReviewQueue() {
  const { data, error, loading, reload } = useApi('/api/calling/review-queue')
  const resolve = async (id: number, status: string) => {
    const notes = status === 'resolved' ? window.prompt('Notes (optional)') ?? undefined : undefined
    await api.post(`/api/calling/review/${id}/resolve`, { status, notes })
    reload()
  }
  return (
    <Page title="Review queue" sub="Leads the engine could not finish on its own">
      <Loading error={error} loading={loading && !data} />
      {data && (data.length ? (
        <div className="card table-wrap"><table>
          <thead><tr><th>Lead</th><th>Reason</th><th>Priority</th><th>Contact</th><th>Added</th><th></th></tr></thead>
          <tbody>{data.map((r: Json) => (
            <tr key={r.id}><td><Link to={`/leads/${r.leadId}`}>{r.companyName}</Link>{r.companyUrl && <div className="small"><a href={r.companyUrl} target="_blank" rel="noreferrer noopener">{r.companyUrl}</a></div>}</td>
              <td>{r.reason.replace(/_/g, ' ')}</td><td><span className={`badge ${r.priority === 'high' ? 'warn' : ''}`}>{r.priority}</span></td>
              <td className="mono small">{r.phone ?? '—'}<br />{r.email ?? ''}</td><td>{fmtDate(r.createdAt)}</td>
              <td className="row"><button className="primary" onClick={() => resolve(r.id, 'resolved')}>Resolved</button><button onClick={() => resolve(r.id, 'skipped')}>Skip</button></td></tr>))}</tbody>
        </table></div>
      ) : <Empty>The review queue is empty.</Empty>)}
    </Page>
  )
}
