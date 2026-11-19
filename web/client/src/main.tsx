import { StrictMode, useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import './styles.css'
import { AuthProvider, useAuth } from './auth'
import { Icon } from './icons'
import Login from './pages/Login'
import Command from './pages/Command'
import Workboard from './pages/Workboard'
import CallMode from './pages/CallMode'
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

type NavItem = [string, string, string, boolean?]   // path, label, icon, adminOnly
const NAV: [string, NavItem[]][] = [
  ['Today', [['/', 'Command deck', 'home'], ['/call', 'Start calling', 'phone'], ['/calls', 'My call list', 'list'], ['/follow-ups', 'Follow-ups', 'clock'], ['/dashboard', 'My numbers', 'chart']]],
  ['Leads', [['/leads', 'All leads', 'inbox'], ['/import', 'Import CSV', 'upload']]],
  ['Shiplystic engine', [['/target', 'Daily target', 'target', true], ['/pipeline', 'Store pipeline', 'funnel', true], ['/controls', 'Suppression & spend', 'shield', true]]],
  ['Team', [['/admin', 'Overview', 'chart', true], ['/admin/assign', 'Assign leads', 'assign', true], ['/admin/users', 'Users', 'users', true], ['/review', 'Review queue', 'list', true]]],
  ['Outreach', [['/outreach', 'Outreach log', 'mail', true], ['/cadence', 'Cadence', 'repeat', true]]],
  ['System', [['/jobs', 'Workers & scrapers', 'server', true], ['/settings', 'Settings', 'cog', true]]],
]
// phone bottom bar: the five things a caller does all day (centre one is the big call button)
const TABS: [string, string, string][] = [
  ['/', 'Home', 'home'], ['/calls', 'My list', 'list'], ['/call', 'Call', 'phone'], ['/follow-ups', 'Follow-ups', 'clock'], ['/dashboard', 'Numbers', 'chart'],
]

function Shell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const isAdmin = me?.role === 'admin'
  useEffect(() => { setOpen(false) }, [loc.pathname])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const brand = <div className="brand"><span className="logo" aria-hidden="true">S</span><div>Shiplystic <span>Leads</span></div></div>
  return (
    <div className="shell">
      <div className="topbar">
        {brand}
        <button onClick={() => setOpen(!open)} aria-label="Menu" aria-expanded={open}><Icon name="menu" /></button>
      </div>
      <div className={`scrim ${open ? 'open' : ''}`} onClick={() => setOpen(false)} />
      <aside className={`side ${open ? 'open' : ''}`} aria-label="Main menu">
        {brand}
        {NAV.map(([group, items]) => {
          const visible = items.filter(([, , , adminOnly]) => !adminOnly || isAdmin)
          if (!visible.length) return null
          return (
            <div key={group}>
              <div className="nav-group">{group}</div>
              <nav className="nav">
                {visible.map(([to, label, icon]) => (
                  <NavLink key={to} to={to} end={to === '/' || to === '/admin'}><Icon name={icon} />{label}</NavLink>
                ))}
              </nav>
            </div>
          )
        })}
        <div className="userbox">
          <b>{me?.fullName}</b>
          <div>{isAdmin ? 'Admin' : 'Sales rep'}</div>
          <button onClick={logout}><Icon name="logout" />Sign out</button>
        </div>
      </aside>
      <main className="main" key={loc.pathname}>{children}</main>
      <nav className="tabbar" aria-label="Quick navigation">
        {TABS.map(([to, label, icon]) => (
          <NavLink key={to} to={to} end={to === '/'} className={to === '/call' ? 'primary-tab' : undefined}>
            {to === '/call' ? <span className="disc"><Icon name={icon} /></span> : <Icon name={icon} />}
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  return me?.role === 'admin' ? <>{children}</> : <div className="notice">This page is for admins.</div>
}

function App() {
  const { me, loading } = useAuth()
  if (loading) return <div className="login-plain muted">Loading…</div>
  if (!me) return <Login />
  const A = (el: ReactNode) => <AdminOnly>{el}</AdminOnly>
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Command />} />
        <Route path="/call" element={<CallMode />} />
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
