import { useState } from 'react'
import { qs } from '../api'
import { useAuth } from '../auth'
import { LeadTable, Loading, Page, Pager, useApi } from '../ui'

export default function Leads() {
  const { me } = useAuth()
  const [f, setF] = useState({ search: '', product: '', tier: '', callStatus: '', city: '', assignedTo: '', sortBy: 'score' })
  const [page, setPage] = useState(1)
  const query = qs({ ...f, page, perPage: 50 })
  const { data, error, loading } = useApi(`/api/leads${query}`)
  const set = (k: string) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setPage(1) }
  return (
    <Page title="All leads" sub={me?.role === 'admin' ? 'Every lead in the database' : 'Leads assigned to you'}
          actions={me?.role === 'admin' && <a className="btn" href={`/api/leads/export${query}`}>Export CSV</a>}>
      <div className="filters">
        <label className="field">Search<input value={f.search} onChange={set('search')} placeholder="Company, person, phone, site" /></label>
        <label className="field">Product<select value={f.product} onChange={set('product')}>
          {['', 'ecom', 'mes', 'dms', 'tms', 'courier', 'calibration'].map(p => <option key={p} value={p}>{p || 'Any'}</option>)}</select></label>
        <label className="field">Score<select value={f.tier} onChange={set('tier')}>
          <option value="">Any</option><option value="hot">Hot (70+)</option><option value="warm">Warm (40-69)</option><option value="cold">Cold</option></select></label>
        <label className="field">Call status<select value={f.callStatus} onChange={set('callStatus')}>
          {['', 'new', 'follow_up', 'no_answer', 'interested', 'not_interested', 'closed'].map(s => <option key={s} value={s}>{s || 'Any'}</option>)}</select></label>
        <label className="field">City<input value={f.city} onChange={set('city')} /></label>
        {me?.role === 'admin' && <label className="field">Assigned<select value={f.assignedTo} onChange={set('assignedTo')}>
          <option value="">Anyone</option><option value="unassigned">Unassigned</option></select></label>}
        <label className="field">Sort<select value={f.sortBy} onChange={set('sortBy')}>
          <option value="score">Score</option><option value="lead_created_at">Newest</option><option value="company_name">Name</option></select></label>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && <div className="card"><LeadTable leads={data.leads} showRep={me?.role === 'admin'} /><Pager page={page} total={data.total} per={50} onPage={setPage} /></div>}
    </Page>
  )
}
