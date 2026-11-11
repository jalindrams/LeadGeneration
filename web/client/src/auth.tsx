import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

export type Me = { id: number; username: string; fullName: string; role: 'admin' | 'sales_rep' }
type Ctx = { me: Me | null; loading: boolean; login: (u: string, p: string) => Promise<void>; logout: () => Promise<void> }

const AuthCtx = createContext<Ctx>(null as unknown as Ctx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try { setMe(await api.get('/api/auth/me')) } catch { setMe(null) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    refresh()
    const onExpired = () => setMe(null)
    window.addEventListener('auth:expired', onExpired)
    return () => window.removeEventListener('auth:expired', onExpired)
  }, [refresh])

  const login = async (username: string, password: string) => {
    await api.post('/api/auth/login', { username, password })
    await refresh()
  }
  const logout = async () => { await api.post('/api/auth/logout'); setMe(null) }

  return <AuthCtx.Provider value={{ me, loading, login, logout }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
