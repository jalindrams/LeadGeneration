import { StrictMode, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import './styles.css'
import { AuthProvider, useAuth } from './auth'
import Login from './pages/Login'
import Command from './pages/Command'
import Workboard from './pages/Workboard'
import LeadDetail from './pages/LeadDetail'
import FollowUps from './pages/FollowUps'
import RepDashboard from './pages/RepDashboard'
import Leads from './pages/Leads'
import ImportCsv from './pages/ImportCsv'
import Target from './pages/Target'
import Pipeline from './pages/Pipeline'
import Controls from './pages/Controls'
import AdminDashboard from './pages/AdminDashboard'
import Users from './pages/Users'
import Assign from './pages/Assign'
import Jobs from './pages/Jobs'
import ReviewQueue from './pages/ReviewQueue'
import Outreach from './pages/Outreach'
import Cadence from './pages/Cadence'
import Settings from './pages/Settings'

type NavItem = [string, string, boolean?]   // path, label, adminOnly
const NAV: [string, NavItem[]][] = [
  ['Today', [['/', 'Command deck'], ['/calls', 'My calls'], ['/follow-ups', 'Follow-ups'], ['/dashboard', 'My numbers']]],
  ['Leads', [['/leads', 'All leads'], ['/import', 'Import CSV']]],
  ['Shiplystic engine', [['/target', 'Daily target', true], ['/pipeline', 'Store pipeline', true], ['/controls', 'Suppression & spend', true]]],
  ['Team', [['/admin', 'Overview', true], ['/admin/assign', 'Assign leads', true], ['/admin/users', 'Users', true], ['/review', 'Review queue', true]]],
  ['Outreach', [['/outreach', 'Outreach log', true], ['/cadence', 'Cadence', true]]],
  ['System', [['/jobs', 'Workers & scrapers', true], ['/settings', 'Settings', true]]],
]

function Shell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const isAdmin = me?.role === 'admin'
  return (
    <div className="shell">
      <div className="topbar"><b>Shiplystic <span style={{ color: 'var(--accent)' }}>Leads</span></b><button onClick={() => setOpen(!open)} aria-label="Menu">☰</button></div>
      <aside className={`side ${open ? 'open' : ''}`} onClick={() => setOpen(false)}>
        <div className="brand">Shiplystic <span>Leads</span></div>
        {NAV.map(([group, items]) => {
          const visible = items.filter(([, , adminOnly]) => !adminOnly || isAdmin)
          if (!visible.length) return null
          return (
            <div key={group}>
              <div className="nav-group">{group}</div>
              <nav className="nav">
                {visible.map(([to, label]) => (
                  <NavLink key={to} to={to} end={to === '/' || to === '/admin'}>{label}</NavLink>
                ))}
              </nav>
            </div>
          )
        })}
        <div className="userbox">
          <div>{me?.fullName}</div>
          <div>{isAdmin ? 'Admin' : 'Sales rep'}</div>
          <button style={{ marginTop: 8 }} onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main" key={loc.pathname}>{children}</main>
    </div>
  )
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  return me?.role === 'admin' ? <>{children}</> : <div className="notice">This page is for admins.</div>
}

function App() {
  const { me, loading } = useAuth()
  if (loading) return <div className="login muted">Loading…</div>
  if (!me) return <Login />
  const A = (el: ReactNode) => <AdminOnly>{el}</AdminOnly>
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Command />} />
        <Route path="/calls" element={<Workboard />} />
        <Route path="/follow-ups" element={<FollowUps />} />
        <Route path="/dashboard" element={<RepDashboard />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/leads/:id" element={<LeadDetail />} />
        <Route path="/import" element={<ImportCsv />} />
        <Route path="/target" element={A(<Target />)} />
        <Route path="/pipeline" element={A(<Pipeline />)} />
        <Route path="/controls" element={A(<Controls />)} />
        <Route path="/admin" element={A(<AdminDashboard />)} />
        <Route path="/admin/users" element={A(<Users />)} />
        <Route path="/admin/assign" element={A(<Assign />)} />
        <Route path="/review" element={A(<ReviewQueue />)} />
        <Route path="/outreach" element={A(<Outreach />)} />
        <Route path="/cadence" element={A(<Cadence />)} />
        <Route path="/jobs" element={A(<Jobs />)} />
        <Route path="/settings" element={A(<Settings />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>
  </StrictMode>,
)
