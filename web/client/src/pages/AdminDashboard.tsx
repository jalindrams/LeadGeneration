import { fmtDate, pct, type Json } from '../api'
import { Bars, Loading, Page, Tile, useApi } from '../ui'

export default function AdminDashboard() {
  const { data, error, loading } = useApi('/api/metrics/summary')
  const { data: trend } = useApi('/api/metrics/trend?days=14')
  const { data: speed } = useApi('/api/metrics/speed-to-lead')
  const { data: perf } = useApi('/api/metrics/source-performance')
  return (
    <Page title="Team overview" sub="All products, all reps">
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="tiles">
          <Tile label="Leads" value={data.total.toLocaleString('en-IN')} sub={`${data.qualified.toLocaleString('en-IN')} qualified`} />
          <Tile label="Hot (70+)" value={data.hot} sub={`${data.warm} warm`} />
          <Tile label="Contacted" value={data.contacted} />
          <Tile label="Interested" value={data.interested} sub={`${data.converted} converted`} />
          <Tile label="Unassigned with phone" value={data.unassignedWithPhone} />
          {speed && <Tile label="Median time to first call" value={speed.medianHours !== null ? `${speed.medianHours} h` : '—'} sub={`last 30 days, ${speed.within24h} within 24 h`} />}
        </div>
      )}
      <div className="grid g2">
        {trend && <div className="card"><h2>Calls per day</h2>
          <Bars label="Calls per day" items={trend.map((d: Json) => ({ key: fmtDate(d.day), value: d.calls, tip: `${fmtDate(d.day)}: ${d.calls} calls, ${d.positive} positive` }))} /></div>}
        {trend && <div className="card"><h2>New leads per day</h2>
          <Bars label="New leads per day" items={trend.map((d: Json) => ({ key: fmtDate(d.day), value: d.leads }))} /></div>}
      </div>
      {data && (
        <div className="card" style={{ marginTop: 14 }}>
          <h2>By product</h2>
          <table><thead><tr><th>Product</th><th className="num">Leads</th><th className="num">Hot</th><th className="num">Contacted</th><th className="num">Interested</th><th className="num">Interest rate</th></tr></thead>
            <tbody>{data.byProduct.map((p: Json) => (
              <tr key={p.product ?? 'none'}><td>{p.product ?? 'unset'}</td><td className="num">{p.total}</td><td className="num">{p.hot}</td>
                <td className="num">{p.contacted}</td><td className="num">{p.interested}</td><td className="num">{p.contacted ? pct(p.interested / p.contacted) : '—'}</td></tr>))}</tbody></table>
        </div>
      )}
      {perf?.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h2>Source performance</h2>
          <div className="table-wrap"><table><thead><tr><th>Source</th><th>Period</th><th className="num">Leads</th><th className="num">Contacted</th><th className="num">Converted</th><th className="num">Response %</th><th>Recommendation</th></tr></thead>
            <tbody>{perf.map((s: Json) => (
              <tr key={s.id}><td>{s.source}</td><td>{fmtDate(s.periodStart)} – {fmtDate(s.periodEnd)}</td><td className="num">{s.totalRaw}</td><td className="num">{s.totalContacted}</td>
                <td className="num">{s.totalConverted}</td><td className="num">{s.responseRate ?? '—'}</td><td><span className="badge">{s.recommendation}</span></td></tr>))}</tbody></table></div>
        </div>
      )}
    </Page>
  )
}
