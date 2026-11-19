import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, fmtTime, qs, type Json } from '../api'
import { Page, TierBadge } from '../ui'

/** Outcome buttons in the order a caller meets them. key = keyboard shortcut. */
const OUTCOMES = [
  { code: 'no_answer', label: 'No answer', key: '1', tone: 'neutral' },
  { code: 'call_back', label: 'Call back later', key: '2', tone: 'neutral' },
  { code: 'not_owner', label: 'Not the decision maker', key: '3', tone: 'neutral' },
  { code: 'interested', label: 'Interested', key: '4', tone: 'good' },
  { code: 'demo_booked', label: 'Demo booked', key: '5', tone: 'good' },
  { code: 'signed_up', label: 'Signed up', key: '6', tone: 'good' },
  { code: 'already_with_competitor', label: 'Happy with current shipper', key: '7', tone: 'bad' },
  { code: 'not_interested', label: 'Not interested', key: '8', tone: 'bad' },
  { code: 'wrong_number', label: 'Wrong number', key: '9', tone: 'bad' },
  { code: 'do_not_call', label: 'Do not call again', key: '0', tone: 'bad' },
] as const

/** One-tap reasons per outcome; the picked ones are saved at the start of the call notes. */
const REASONS: Record<string, string[]> = {
  call_back: ['Busy right now', 'In a meeting', 'Call in evening', 'Owner travelling'],
  not_owner: ['Got owner name', 'Got owner number', 'Owner not available', 'Staff will pass message'],
  interested: ['Wants pricing', 'Wants COD remittance details', 'High RTO problem', 'Wants multiple couriers', 'Send WhatsApp details'],
  demo_booked: ['Demo today', 'Demo tomorrow', 'Demo this week'],
  signed_up: ['Signed up on call', 'Will sign up today'],
  already_with_competitor: ['Shiprocket', 'Delhivery', 'NimbusPost', 'iThink Logistics', 'Shipway', 'ClickPost', 'Pickrr', 'Own courier contract', 'Other'],
  not_interested: ['Low order volume', 'Price concern', 'Local delivery only', 'Not selling online now', 'Shutting down', 'No reason given'],
  wrong_number: ['Not in service', 'Different business', 'Personal number', 'Switched off for days'],
  do_not_call: ['Asked to remove number', 'Angry / complained'],
  no_answer: ['Ringing, no answer', 'Busy tone', 'Switched off', 'Cut the call'],
}

/** Outcomes that need a follow-up date, with the default offered. */
const NEEDS_DATE: Record<string, number> = { call_back: 1, not_owner: 2, interested: 2, demo_booked: 1 }
const DATE_CHIPS: [string, number][] = [['Today', 0], ['Tomorrow', 1], ['In 2 days', 2], ['Next week', 7]]

const iso = (daysAhead: number) => {
  const d = new Date(); d.setDate(d.getDate() + daysAhead)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const PRODUCT_KEY = 'callmode.product'
const SKIP_KEY = 'callmode.skip'
function readStore(k: string, fallback: string) { try { return localStorage.getItem(k) ?? fallback } catch { return fallback } }
function writeStore(k: string, v: string) { try { localStorage.setItem(k, v) } catch { /* private window */ } }
function readSkip(): string[] { try { return JSON.parse(sessionStorage.getItem(SKIP_KEY) || '[]') } catch { return [] } }
function writeSkip(ids: string[]) { try { sessionStorage.setItem(SKIP_KEY, JSON.stringify(ids.slice(-200))) } catch { /* ignore */ } }

const REASON_LABEL: Record<string, string> = { follow_up: 'Follow-up due', new: 'New lead', retry: 'No answer earlier, retry' }

export default function CallMode() {
  const [product, setProduct] = useState(() => readStore(PRODUCT_KEY, 'ecom'))
  const [next, setNext] = useState<Json | null>(null)
  const [lead, setLead] = useState<Json | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [outcome, setOutcome] = useState<string | null>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const [followUp, setFollowUp] = useState('')
  const [notes, setNotes] = useState('')
  const [contactName, setContactName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [lastSaved, setLastSaved] = useState<string | null>(null)
  const notesRef = useRef<HTMLTextAreaElement>(null)

  const resetForm = () => { setOutcome(null); setReasons([]); setFollowUp(''); setNotes(''); setContactName(''); setSaveError(null) }

  const load = useCallback(async () => {
    setLoading(true); setLoadError(null)
    try {
      const n = await api.get(`/api/calling/next${qs({ product, skip: readSkip().join(',') })}`)
      setNext(n)
      setLead(n.leadId ? await api.get(`/api/leads/${n.leadId}`) : null)
      resetForm()
    } catch (e) {
      setLoadError((e as Error).message === 'Failed to fetch' ? 'No connection to the server. Check the network and try again.' : (e as Error).message)
    } finally { setLoading(false) }
  }, [product])

  useEffect(() => { load() }, [load])

  const pick = (code: string) => {
    setOutcome(code); setReasons([]); setSaveError(null)
    setFollowUp(code in NEEDS_DATE ? iso(NEEDS_DATE[code]) : '')
  }
  const toggleReason = (r: string) => setReasons(rs => (rs.includes(r) ? rs.filter(x => x !== r) : [...rs, r]))

  const save = useCallback(async () => {
    if (!outcome || !lead || saving) return
    if (outcome in NEEDS_DATE && !followUp) { setSaveError('Pick a follow-up date.'); return }
    setSaving(true); setSaveError(null)
    const reasonText = reasons.length ? (outcome === 'already_with_competitor' ? `Uses: ${reasons.join(', ')}` : reasons.join(', ')) : ''
    const remarks = [reasonText, notes.trim()].filter(Boolean).join('. ') || null
    try {
      await api.post(`/api/calling/leads/${lead.lead.id}/call`, {
        outcome, remarks, followUpDate: followUp || null,
        decisionMaker: contactName.trim() || null,
        painPoint: outcome === 'interested' && reasons.length ? reasons.join(', ') : null,
      })
      setLastSaved(`${lead.lead.companyName}: ${OUTCOMES.find(o => o.code === outcome)?.label}`)
      await load()
    } catch (e) {
      // Keep everything the caller typed so a retry loses nothing.
      setSaveError((e as Error).message === 'Failed to fetch' ? 'Not saved: no connection. Your entry is kept, press Save again.' : `Not saved: ${(e as Error).message}`)
    } finally { setSaving(false) }
  }, [outcome, lead, saving, followUp, reasons, notes, contactName, load])

  const skip = () => {
    if (!lead) return
    writeSkip([...readSkip(), lead.lead.id])
    load()
  }
  const clearSkips = () => { writeSkip([]); load() }

  // Keyboard: 1–0 pick an outcome, Ctrl+Enter saves. Ignored while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest('input, textarea, select')
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); return }
      if (typing) return
      const o = OUTCOMES.find(x => x.key === e.key)
      if (o && lead) pick(o.code)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [save, lead])

  const c = next?.counts
  const l = lead?.lead
  const ev = lead?.evidence

  return (
    <Page title="Call mode" sub="One lead at a time. Call, tap what happened, save, and the next lead opens."
          actions={<label className="field" style={{ minWidth: 170 }}>Product
            <select value={product} onChange={e => { setProduct(e.target.value); writeStore(PRODUCT_KEY, e.target.value) }}>
              <option value="ecom">Shiplystic (ecommerce)</option>
              <option value="">All products</option>
              <option value="mes">MES</option><option value="dms">DMS</option><option value="tms">TMS</option>
              <option value="courier">Courier MS</option><option value="calibration">Calibration MS</option>
            </select></label>}>

      {c && (
        <div className="cm-counts">
          <span><b>{next.callsToday}</b> calls today</span>
          <span><b>{c.due}</b> follow-ups due</span>
          <span><b>{c.fresh}</b> new</span>
          <span><b>{c.retry}</b> to retry</span>
          {lastSaved && <span className="muted">Saved: {lastSaved}</span>}
        </div>
      )}

      {loadError && (
        <div className="notice error" style={{ marginBottom: 12 }}>
          {loadError} <button onClick={load} style={{ marginLeft: 8 }}>Try again</button>
        </div>
      )}
      {loading && !lead && !loadError && <div className="muted">Finding your next lead…</div>}

      {!loading && !loadError && next && !next.leadId && (
        <div className="card cm-empty">
          <h2>No more leads to call right now</h2>
          <p className="muted">Your follow-ups, new leads and retries are all done{product ? ' for this product' : ''}, and there are no unassigned leads left to take.
            No-answer leads come back here three hours after the last try.</p>
          <div className="row">
            <button onClick={load}>Check again</button>
            {readSkip().length > 0 && <button onClick={clearSkips}>Show the {readSkip().length} I skipped</button>}
            <Link className="btn" to="/calls">Open my call list</Link>
          </div>
        </div>
      )}

      {l && (
        <div className="cm-grid" style={{ opacity: loading ? 0.5 : 1 }}>
          <div className="card cm-lead">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="badge">{REASON_LABEL[next.reason] ?? 'Lead'}{l.followUpDate && next.reason === 'follow_up' ? ` · ${fmtDate(l.followUpDate)}` : ''}</span>
              <TierBadge tier={ev?.store?.tier ?? l.tier} />
            </div>
            <h2 className="cm-company">{l.companyName}</h2>
            <div className="muted">{[l.fullName, l.title, l.location].filter(Boolean).join(' · ') || 'Contact name unknown'}</div>
            {l.phone
              ? <a className="cm-dial" href={`tel:${l.phone}`}>📞 {l.phone}</a>
              : <div className="cm-dial off">No phone number</div>}
            <div className="small muted">Tap the number to dial from your phone, or dial it from your desk phone.</div>
            {lead.opener && <><h3>Say this first</h3><div className="opener">{lead.opener}</div></>}
            <dl className="kv" style={{ marginTop: 12 }}>
              {l.companyUrl && <><dt>Website</dt><dd><a href={l.companyUrl} target="_blank" rel="noreferrer noopener">{l.companyUrl.replace(/^https?:\/\//, '')}</a></dd></>}
              {ev?.store?.competitorTool && <><dt>Ships with</dt><dd>{ev.store.competitorTool}</dd></>}
              {ev?.store?.productCount != null && <><dt>Products</dt><dd>{ev.store.productCount}</dd></>}
              {l.decisionMaker && <><dt>Decision maker</dt><dd>{l.decisionMaker}</dd></>}
              <dt>Calls so far</dt><dd>{l.callCount ?? 0}</dd>
            </dl>
            {lead.calls?.length > 0 && (
              <>
                <h3>Earlier calls</h3>
                <ul className="cm-history">{lead.calls.slice(0, 4).map((h: Json) => (
                  <li key={h.id}><b>{h.callStatus.replace(/_/g, ' ')}</b> · {fmtTime(h.calledAt)} · {h.calledBy}{h.remarks ? <div className="small muted">{h.remarks}</div> : null}</li>
                ))}</ul>
              </>
            )}
            <div className="row" style={{ marginTop: 12 }}>
              <Link className="btn" to={`/leads/${l.id}`}>Full details</Link>
              <button onClick={skip} disabled={loading}>Skip for now</button>
            </div>
          </div>

          <div className="card cm-log">
            <h2>What happened?</h2>
            <div className="cm-outcomes">
              {OUTCOMES.map(o => (
                <button key={o.code} className={`cm-out ${o.tone} ${outcome === o.code ? 'sel' : ''}`} onClick={() => pick(o.code)}>
                  <span className="cm-key">{o.key}</span>{o.label}
                </button>
              ))}
            </div>

            {outcome && (
              <>
                {REASONS[outcome] && (
                  <>
                    <h3>{outcome === 'already_with_competitor' ? 'Which shipper do they use?' : 'Reason (tap all that apply)'}</h3>
                    <div className="chips">{REASONS[outcome].map(r => (
                      <button key={r} className={`chip ${reasons.includes(r) ? 'sel' : ''}`} onClick={() => toggleReason(r)}>{r}</button>
                    ))}</div>
                  </>
                )}
                {outcome in NEEDS_DATE && (
                  <>
                    <h3>Call again on</h3>
                    <div className="chips">
                      {DATE_CHIPS.map(([label, d]) => (
                        <button key={label} className={`chip ${followUp === iso(d) ? 'sel' : ''}`} onClick={() => setFollowUp(iso(d))}>{label}</button>
                      ))}
                      <input type="date" value={followUp} min={iso(0)} onChange={e => setFollowUp(e.target.value)} aria-label="Follow-up date" />
                    </div>
                  </>
                )}
                {(outcome === 'not_owner' || outcome === 'interested' || outcome === 'demo_booked') && (
                  <label className="field" style={{ marginTop: 12 }}>Decision maker name / number (optional)
                    <input value={contactName} onChange={e => setContactName(e.target.value)} placeholder="e.g. Rahul (owner) 98xxxxxxxx" />
                  </label>
                )}
                <label className="field" style={{ marginTop: 12 }}>Notes (optional)
                  <textarea ref={notesRef} rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
                </label>
              </>
            )}

            {saveError && <div className="notice error" style={{ marginTop: 12 }}>{saveError}</div>}
            <button className="primary cm-save" disabled={!outcome || saving || loading} onClick={save}>
              {saving ? 'Saving…' : outcome ? 'Save & next lead' : 'Pick what happened first'}
            </button>
            <div className="small muted" style={{ marginTop: 6 }}>Shortcut keys: 1–0 pick an outcome, Ctrl+Enter saves.</div>
          </div>
        </div>
      )}
    </Page>
  )
}
