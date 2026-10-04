import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setSessionExpiredHandler, tokenStore } from '@/lib/api'
import type { AuthResponse, Company, User } from '@/lib/types'

export interface SignupInput {
  company_name: string
  company_gstin?: string
  full_name: string
  email: string
  password: string
}

interface AuthState {
  user: User | null
  company: Company | null
  status: 'loading' | 'authenticated' | 'anonymous'
  login: (email: string, password: string) => Promise<void>
  signup: (input: SignupInput) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [company, setCompany] = useState<Company | null>(null)
  const [status, setStatus] = useState<AuthState['status']>(
    tokenStore.get() ? 'loading' : 'anonymous',
  )
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const clear = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    setCompany(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  // Restore the session on load.
  useEffect(() => {
    if (!tokenStore.get()) return
    api<{ user: User; company: Company }>('/auth/me')
      .then((me) => {
        setUser(me.user)
        setCompany(me.company)
        setStatus('authenticated')
      })
      .catch(() => clear())
  }, [clear])

  // Expired/invalid token anywhere in the app -> back to login, remembering where we were.
  useEffect(() => {
    setSessionExpiredHandler((reason) => {
      clear()
      const next = encodeURIComponent(window.location.pathname + window.location.search)
      navigate(`/login?reason=${reason}&next=${next}`, { replace: true })
    })
    return () => setSessionExpiredHandler(null)
  }, [clear, navigate])

  const accept = useCallback((auth: AuthResponse) => {
    tokenStore.set(auth.access_token)
    setUser(auth.user)
    setCompany(auth.company)
    setStatus('authenticated')
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      accept(await api<AuthResponse>('/auth/login', { method: 'POST', body: { email, password } }))
    },
    [accept],
  )

  const signup = useCallback(
    async (input: SignupInput) => {
      const body = { ...input, company_gstin: input.company_gstin?.trim() || null }
      accept(await api<AuthResponse>('/auth/signup', { method: 'POST', body }))
    },
    [accept],
  )

  const logout = useCallback(() => {
    clear()
    navigate('/login', { replace: true })
  }, [clear, navigate])

  const value = useMemo(
    () => ({ user, company, status, login, signup, logout }),
    [user, company, status, login, signup, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
