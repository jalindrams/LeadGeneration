import { useState } from 'react'
import { api, qs, type Json } from '../api'
import { Page, useApi } from '../ui'

export default function Assign() {
  const { data: reps } = useApi('/api/calling/reps')
  const [f, setF] = useState({ product: 'ecom', city: '', industry: '', minScore: '', source: '' })
  const [userId, setUserId] = useState('')
  const [count, setCount] = useState(50)
  const [msg, setMsg] = useState<string | null>(null)
  const { data: preview, reload } = useApi(`/api/admin/assign-preview${qs(f)}`)
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const go = async () => {
    setMsg(null)
    try {
      const r = await api.post('/api/admin/assign-bulk', { userId: Number(userId), count, product: f.product || null, city: f.city || null,
        industry: f.industry || null, minScore: f.minScore ? Number(f.minScore) : null, source: f.source || null })
      setMsg(`Assigned ${r.assigned} leads.`); reload()
    } catch (e) { setMsg((e as Error).message) }
  }
  return (
    <Page title="Assign leads" sub="Hands the highest-scoring unassigned leads with a phone number to a rep">
      <div className="card stack" style={{ maxWidth: 820 }}>
        <div className="filters">
          <label className="field">Product<select value={f.product} onChange={set('product')}>{['', 'ecom', 'mes', 'dms', 'tms', 'courier', 'calibration'].map(p => <option key={p} value={p}>{p || 'Any'}</option>)}</select></label>
          <label className="field">City<input value={f.city} onChange={set('city')} /></label>
          <label className="field">Industry<input value={f.industry} onChange={set('industry')} /></label>
          <label className="field">Min score<input type="number" value={f.minScore} onChange={set('minScore')} style={{ width: 90 }} /></label>
          <label className="field">Source<input value={f.source} onChange={set('source')} placeholder="e.g. ecom:tranco_in" /></label>
        </div>
        <div className="muted">{preview ? `${preview.available} unassigned leads with a phone match these filters.` : '…'}</div>
        <div className="filters">
          <label className="field">Rep<select value={userId} onChange={e => setUserId(e.target.value)}>
            <option value="">Choose…</option>{reps?.map((r: Json) => <option key={r.id} value={r.id}>{r.fullName}</option>)}</select></label>
          <label className="field">How many<input type="number" min={1} max={1000} value={count} onChange={e => setCount(Number(e.target.value))} style={{ width: 100 }} /></label>
          <button className="primary" disabled={!userId || !preview?.available} onClick={go}>Assign</button>
        </div>
        {msg && <div className="notice">{msg}</div>}
      </div>
    </Page>
  )
}
