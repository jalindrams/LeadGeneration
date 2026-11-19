import { useState } from 'react'
import { api, type Json } from '../api'
import { useAuth } from '../auth'
import { Page } from '../ui'

export default function ImportCsv() {
  const { me } = useAuth()
  const [file, setFile] = useState<File | null>(null)
  const [product, setProduct] = useState('ecom')
  const [res, setRes] = useState<Json>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    if (!file) return
    setBusy(true); setErr(null); setRes(null)
    const form = new FormData(); form.append('file', file)
    try { setRes(await api.upload(`/api/calling/import-csv?product=${product}`, form)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Page title="Import CSV" sub={me?.role === 'admin' ? 'Imported leads stay unassigned until you assign them' : 'Imported leads are assigned to you'}>
      <div className="card stack" style={{ maxWidth: 640 }}>
        <p className="muted" style={{ margin: 0 }}>
          Columns: <span className="mono">company_name</span> (required), and any of <span className="mono">phone, email, full_name, title, city, industry, website</span>.
          Duplicates (same company and phone) are skipped.
        </p>
        <label className="field">CSV file<input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
        <label className="field">Product<select value={product} onChange={e => setProduct(e.target.value)}>
          {['ecom', 'mes', 'dms', 'tms', 'courier', 'calibration'].map(p => <option key={p}>{p}</option>)}</select></label>
        <div><button className="primary" disabled={!file || busy} onClick={go}>{busy ? 'Importing…' : 'Import'}</button></div>
        {err && <div className="error-text">{err}</div>}
        {res && <div className="notice">Added {res.added} · duplicates skipped {res.duplicates} · rows without a company {res.skipped}. <span className="muted">{res.note}</span></div>}
      </div>
    </Page>
  )
}
