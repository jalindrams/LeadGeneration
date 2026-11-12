import { Loading, Page, Tile, useApi } from '../ui'
import { pct } from '../api'

export default function RepDashboard() {
  const { data, error, loading } = useApi('/api/calling/dashboard')
  const { data: stats } = useApi('/api/leads/stats')
  return (
    <Page title="My numbers" sub="Today, and the leads assigned to you">
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="tiles">
            <Tile label="Calls today" value={data.callsToday} />
            <Tile label="Reached a person" value={data.reachedToday} sub={data.callsToday ? `${pct(data.reachedToday / data.callsToday)} of calls` : undefined} />
            <Tile label="Interested / demo / signed" value={data.positiveToday} />
            <Tile label="Wrong numbers" value={data.wrongToday} />
            <Tile label="Follow-ups due" value={data.followUpsDue} />
            <Tile label="Not yet called" value={data.queue} />
          </div>
          <div className="grid g2">
            <div className="card">
              <h2>Today's outcomes</h2>
              {data.byOutcome?.length ? (
                <table><tbody>{data.byOutcome.map((o: { key: string; count: number }) =>
                  <tr key={o.key}><td>{o.key.replace(/_/g, ' ')}</td><td className="num">{o.count}</td></tr>)}</tbody></table>
              ) : <div className="muted">No calls yet today.</div>}
            </div>
            {stats && (
              <div className="card">
                <h2>My leads</h2>
                <table><tbody>
                  <tr><td>Total</td><td className="num">{stats.total}</td></tr>
                  <tr><td>Hot (score 70+)</td><td className="num">{stats.hot}</td></tr>
                  {stats.byCallStatus.map((s: { key: string | null; count: number }) =>
                    <tr key={s.key ?? 'none'}><td>Status: {s.key ?? 'new'}</td><td className="num">{s.count}</td></tr>)}
                </tbody></table>
              </div>
            )}
          </div>
        </>
      )}
    </Page>
  )
}
