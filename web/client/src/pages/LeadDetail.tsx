import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, fmtDate, fmtTime, type Json } from '../api'
import { useAuth } from '../auth'
import { Loading, Page, TierBadge, useApi } from '../ui'

export default function LeadDetail() {
  const { id } = useParams()
  const { me } = useAuth()
  const { data, error, loading, reload } = useApi(`/api/leads/${id}`)
  const { data: meta } = useApi('/api/calling/meta')
  const { data: reps } = useApi('/api/calling/reps')
  const [outcome, setOutcome] = useState<string | null>(null)
  const [remarks, setRemarks] = useState('')
  const [followUp, setFollowUp] = useState('')
  const [decisionMaker, setDecisionMaker] = useState('')
  const [painPoint, setPainPoint] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [transferTo, setTransferTo] = useState('')

  if (!data) return <Loading error={error} loading={loading} />
  const l = data.lead
  const ev = data.evidence

  const save = async () => {
    if (!outcome) return
    setBusy(true); setMsg(null)
    try {
      await api.post(`/api/calling/leads/${id}/call`, {
        outcome, remarks: remarks || null, followUpDate: followUp || null,
        decisionMaker: decisionMaker || null, painPoint: painPoint || null,
      })
      setMsg('Saved.'); setOutcome(null); setRemarks(''); setFollowUp('')
      reload()
    } catch (e) { setMsg((e as Error).message) } finally { setBusy(false) }
  }
  const transfer = async () => {
    if (!transferTo) return
    try { await api.post(`/api/calling/leads/${id}/transfer`, { toUserId: Number(transferTo) }); setMsg('Transferred.'); reload() }
    catch (e) { setMsg((e as Error).message) }
  }

  return (
    <Page title={l.companyName} sub={<>{l.targetProduct ?? 'no product'} · score {l.score ?? 0} <TierBadge tier={l.tier} />{ev?.store?.tier && <> <TierBadge tier={ev.store.tier} /></>}</>}
          actions={<Link className="btn" to="/calls">Back to calls</Link>}>
      <div className="grid g2">
        <div className="stack">
          <div className="card">
            <div className="phone-big mono">{l.phone ? <a href={`tel:${l.phone}`}>{l.phone}</a> : 'No phone'}</div>
            <div className="muted">{l.fullName ?? 'Contact name unknown'}{l.title ? ` · ${l.title}` : ''}</div>
            {l.companyUrl && <div style={{ marginTop: 6 }}><a href={l.companyUrl} target="_blank" rel="noreferrer noopener">{l.companyUrl}</a></div>}
            {data.opener && <><h2 style={{ marginTop: 14 }}>Suggested opening</h2><div className="opener">{data.opener}</div></>}
          </div>

          <div className="card">
            <h2>Log this call</h2>
            <div className="outcomes">
              {meta?.outcomes?.map((o: Json) => (
                <button key={o.code} className={outcome === o.code ? 'sel' : ''} onClick={() => setOutcome(o.code)}>{o.label}</button>
              ))}
            </div>
            <div className="grid g2" style={{ marginTop: 12 }}>
              <label className="field">Follow-up date<input type="date" value={followUp} onChange={e => setFollowUp(e.target.value)} /></label>
              <label className="field">Decision maker<input value={decisionMaker} onChange={e => setDecisionMaker(e.target.value)} placeholder={l.decisionMaker ?? ''} /></label>
            </div>
            <label className="field" style={{ marginTop: 10 }}>Current shipping pain<input value={painPoint} onChange={e => setPainPoint(e.target.value)} placeholder={l.painPoint ?? 'e.g. high RTO, slow COD remittance'} /></label>
            <label className="field" style={{ marginTop: 10 }}>Notes<textarea value={remarks} onChange={e => setRemarks(e.target.value)} /></label>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" disabled={!outcome || busy} onClick={save}>{busy ? 'Saving…' : 'Save call'}</button>
              {msg && <span className={msg.endsWith('.') ? 'muted' : 'error-text'}>{msg}</span>}
            </div>
          </div>

          <div className="card">
            <h2>Call history</h2>
            {data.calls?.length ? (
              <table><tbody>{data.calls.map((c: Json) => (
                <tr key={c.id}><td>{fmtTime(c.calledAt)}</td><td>{c.callStatus.replace(/_/g, ' ')}</td><td>{c.calledBy}</td><td className="small">{c.remarks}</td></tr>
              ))}</tbody></table>
            ) : <div className="muted">Not called yet.</div>}
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <h2>Lead</h2>
            <dl className="kv">
              <dt>Status</dt><dd>{l.callStatus ?? 'new'}{l.responseStatus ? ` · ${l.responseStatus}` : ''}</dd>
              <dt>Follow-up</dt><dd>{fmtDate(l.followUpDate)}</dd>
              <dt>City</dt><dd>{l.location ?? '—'}</dd>
              <dt>Industry</dt><dd>{l.industry ?? '—'}</dd>
              <dt>Email</dt><dd>{l.email ?? '—'}</dd>
              <dt>GSTIN</dt><dd className="mono">{l.gstNumber ?? '—'}</dd>
              <dt>Source</dt><dd>{l.source}</dd>
              <dt>Assigned to</dt><dd>{l.assignedName ?? 'unassigned'}</dd>
              <dt>Calls</dt><dd>{l.callCount ?? 0}</dd>
            </dl>
            {(me?.role === 'admin' || l.assignedTo === me?.id) && reps && (
              <div className="row" style={{ marginTop: 12 }}>
                <select value={transferTo} onChange={e => setTransferTo(e.target.value)}>
                  <option value="">Transfer to…</option>
                  {reps.filter((r: Json) => r.id !== l.assignedTo).map((r: Json) => <option key={r.id} value={r.id}>{r.fullName}</option>)}
                </select>
                <button disabled={!transferTo} onClick={transfer}>Transfer</button>
              </div>
            )}
          </div>

          {ev && (
            <div className="card">
              <h2>Why this lead (evidence)</h2>
              <dl className="kv">
                <dt>Store</dt><dd><a href={`https://${ev.store.domain}`} target="_blank" rel="noreferrer noopener">{ev.store.domain}</a></dd>
                <dt>Platform</dt><dd>{ev.store.platform ?? '—'}</dd>
                <dt>Products</dt><dd>{ev.store.productCount ?? '—'}</dd>
                <dt>Ships with</dt><dd>{ev.store.competitorTool ?? 'not detected'}</dd>
                <dt>Found via</dt><dd>{ev.store.source}{ev.store.sourceRef && <div className="small muted">{ev.store.sourceRef}</div>}</dd>
                {ev.store.sourceNote && <><dt>Note</dt><dd className="small">{ev.store.sourceNote}</dd></>}
              </dl>
              <h2 style={{ marginTop: 14 }}>Contacts found</h2>
              <div className="table-wrap"><table>
                <thead><tr><th>Phone / email</th><th>Type</th><th>From</th></tr></thead>
                <tbody>{ev.contacts.map((c: Json) => (
                  <tr key={c.id}><td className="mono">{c.phone ?? c.email ?? c.name}{c.isPrimary && <span className="badge ok" style={{ marginLeft: 6 }}>primary</span>}</td>
                    <td>{c.phoneType ?? c.role ?? '—'}</td>
                    <td className="small">{c.sourceUrl?.startsWith('http') ? <a href={c.sourceUrl} target="_blank" rel="noreferrer noopener">{c.sourceUrl}</a> : c.sourceUrl}</td></tr>
                ))}</tbody>
              </table></div>
            </div>
          )}
          {l.remarks && <div className="card"><h2>Notes</h2><pre className="log">{l.remarks}</pre></div>}
        </div>
      </div>
    </Page>
  )
}
