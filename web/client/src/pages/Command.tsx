import { Link } from 'react-router-dom'
import { fmtTime } from '../api'
import { useAuth } from '../auth'
import { Empty, LeadTable, Loading, Meter, Page, Tile, useApi } from '../ui'

export default function Command() {
  const { me } = useAuth()
  const { data, error, loading } = useApi('/api/command/deck')
  const k = data?.kpis
  return (
    <Page title={`Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}, ${me?.fullName.split(' ')[0]}`}
          sub={new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}
          actions={<Link className="btn primary" to="/call">Start calling</Link>}>
      <Loading error={error} loading={loading && !data} />
      {k && (
        <>
          <div className="tiles">
            <Tile label="Calls today" value={k.callsToday} sub={`${k.reachedToday} reached a person`} />
            <Tile label="Interested / demos" value={k.positiveToday} sub={`${k.demosToday} demos booked`} />
            <Tile label="Follow-ups due" value={k.followUpsDue} sub={<Link to="/follow-ups">Open list</Link>} />
            <Tile label="New leads today" value={k.newLeadsToday} />
          </div>
          {me?.role === 'admin' && (
            <div className="card" style={{ marginBottom: 14 }}>
              <Meter label="Today's Shiplystic batch" value={k.batchDelivered} max={k.batchTarget} />
              {k.batchDelivered < k.batchTarget && <div className="small muted" style={{ marginTop: 6 }}>Batch is short. See <Link to="/target">Daily target</Link>.</div>}
            </div>
          )}
          {data.failing?.length > 0 && (
            <div className="notice error" style={{ marginBottom: 14 }}>
              <b>Sources needing attention:</b>
              <ul style={{ margin: '6px 0 0' }}>{data.failing.map((f: { source: string; error: string; startedAt: string }, i: number) =>
                <li key={i}>{f.source} · {fmtTime(f.startedAt)} · <span className="small">{(f.error || '').slice(0, 140)}</span></li>)}</ul>
            </div>
          )}
          <div className="grid g2">
            <div className="card"><h2>Hot leads not yet called</h2><LeadTable leads={data.hot} showRep={me?.role === 'admin'} /></div>
            <div className="card"><h2>Follow-ups due</h2><LeadTable leads={data.due} showRep={me?.role === 'admin'} /></div>
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h2>Recent calls</h2>
            {data.recent?.length ? (
              <div className="table-wrap"><table>
                <thead><tr><th>When</th><th>Company</th><th>Outcome</th><th>By</th><th>Notes</th></tr></thead>
                <tbody>{data.recent.map((r: { leadId: string; calledAt: string; companyName: string; callStatus: string; calledBy: string; remarks: string }, i: number) => (
                  <tr key={i}><td>{fmtTime(r.calledAt)}</td><td><Link to={`/leads/${r.leadId}`}>{r.companyName}</Link></td>
                    <td>{r.callStatus.replace(/_/g, ' ')}</td><td>{r.calledBy}</td><td className="small">{r.remarks}</td></tr>))}</tbody>
              </table></div>
            ) : <Empty>No calls logged today yet.</Empty>}
          </div>
        </>
      )}
    </Page>
  )
}
