import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, type Json } from './api'

/** Load JSON from the API; returns data, error, loading and a reload function. */
export function useApi<T = Json>(url: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    if (!url) return
    setLoading(true)
    try { setData(await api.get(url)); setError(null) } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, ...deps])
  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load }
}

export function Page({ title, sub, actions, children }: { title: string; sub?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  useEffect(() => { document.title = `${title} · Shiplystic Leads` }, [title])
  return (
    <>
      <div className="page-head">
        <div><h1>{title}</h1>{sub && <div className="muted">{sub}</div>}</div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {children}
    </>
  )
}

export function Tile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return <div className="tile"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>
}

export function Loading({ error, loading }: { error?: string | null; loading?: boolean }) {
  if (error) return <div className="notice error">Could not load: {error}</div>
  if (loading) return <div className="muted">Loading…</div>
  return null
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="notice muted">{children}</div>
}

export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const w = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      <div className="spread small"><span>{label}</span><span className="mono">{value} / {max}</span></div>
      <div className="meter" role="meter" aria-valuenow={value} aria-valuemax={max} aria-label={label}><div style={{ width: `${w}%` }} /></div>
    </div>
  )
}

/** Single-series bar chart with hover tooltips; bars under target use the muted step. */
export function Bars({ items, target, label }: { items: { key: string; value: number; tip?: string }[]; target?: number; label: string }) {
  const max = Math.max(target ?? 0, ...items.map(i => i.value), 1)
  return (
    <figure style={{ margin: 0 }}>
      <div className="bars" aria-label={label} role="img">
        {items.map(i => (
          <div key={i.key} className={`b ${target !== undefined && i.value < target ? 'under' : ''}`}>
            <span className="tip">{i.tip ?? `${i.key}: ${i.value}`}</span>
            <div style={{ height: `${(i.value / max) * 100}%` }} />
          </div>
        ))}
      </div>
      {items.length > 0 && <div className="bar-axis"><span>{items[0].key}</span><span>{items[items.length - 1].key}</span></div>}
      <details className="small muted" style={{ marginTop: 6 }}>
        <summary>Show as table</summary>
        <table><tbody>{items.map(i => <tr key={i.key}><td>{i.key}</td><td className="num">{i.value}</td></tr>)}</tbody></table>
      </details>
    </figure>
  )
}

export function TierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return <span className="muted">—</span>
  return <span className={`badge ${tier}`} title={tier === 'A' ? 'Switcher: uses or reviewed a competitor' : tier === 'B' ? 'Growing store' : tier}>{tier === 'hot' ? 'Hot' : tier === 'warm' ? 'Warm' : tier === 'cold' ? 'Cold' : `Tier ${tier}`}</span>
}

export function StatusBadge({ ok, children }: { ok: boolean | null; children: ReactNode }) {
  return <span className={`badge ${ok === null ? 'warn' : ok ? 'ok' : 'fail'}`}>{children}</span>
}

export function LeadTable({ leads, showRep = false }: { leads: Json[]; showRep?: boolean }) {
  if (!leads?.length) return <Empty>No leads here.</Empty>
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Company</th><th>Phone</th><th>City</th><th>Product</th><th className="num">Score</th><th>Status</th><th>Follow-up</th>{showRep && <th>Rep</th>}</tr></thead>
      <tbody>
        {leads.map(l => (
          <tr key={l.id}>
            <td><Link to={`/leads/${l.id}`}>{l.companyName}</Link>{l.fullName && <div className="small muted">{l.fullName}{l.title ? ` · ${l.title}` : ''}</div>}</td>
            <td className="mono">{l.phone || '—'}</td>
            <td>{l.location || '—'}</td>
            <td>{l.targetProduct || '—'}</td>
            <td className="num">{l.score ?? 0} <TierBadge tier={l.tier} /></td>
            <td>{l.callStatus || 'new'}</td>
            <td>{fmtDate(l.followUpDate)}</td>
            {showRep && <td>{l.assignedName || <span className="muted">unassigned</span>}</td>}
          </tr>
        ))}
      </tbody>
    </table></div>
  )
}

export function Pager({ page, total, per, onPage }: { page: number; total: number; per: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / per))
  return (
    <div className="spread small" style={{ marginTop: 10 }}>
      <span className="muted">{total.toLocaleString('en-IN')} total</span>
      <div className="row">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span>Page {page} of {pages}</span>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  )
}
