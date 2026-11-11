import { useState } from 'react'
import { qs } from '../api'
import { useAuth } from '../auth'
import { LeadTable, Loading, Page, Pager, useApi } from '../ui'

const VIEWS: [string, string][] = [['', 'To call now'], ['follow_up', 'Follow-ups'], ['retry', 'No answer, retry'], ['done', 'Finished']]
const PRODUCTS = ['', 'ecom', 'mes', 'dms', 'tms', 'courier', 'calibration']

export default function Workboard({ initialView = '' }: { initialView?: string }) {
  const { me } = useAuth()
  const [view, setView] = useState(initialView)
  const [product, setProduct] = useState('')
  const [page, setPage] = useState(1)
  const { data, error, loading } = useApi(`/api/calling/workboard${qs({ view, product, page })}`)
  return (
    <Page title={initialView === 'follow_up' ? 'Follow-ups' : 'My calls'} sub="Due follow-ups first, then the highest-scoring new leads">
      <div className="tabs">{VIEWS.map(([v, l]) => <button key={v} className={view === v ? 'on' : ''} onClick={() => { setView(v); setPage(1) }}>{l}</button>)}</div>
      <div className="filters">
        <label className="field">Product<select value={product} onChange={e => { setProduct(e.target.value); setPage(1) }}>
          {PRODUCTS.map(p => <option key={p} value={p}>{p || 'All products'}</option>)}</select></label>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && <div className="card"><LeadTable leads={data.leads} showRep={me?.role === 'admin'} /><Pager page={page} total={data.total} per={50} onPage={setPage} /></div>}
    </Page>
  )
}
