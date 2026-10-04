import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { LoadingState } from '@/components/ui'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <LoadingState label="Signing you in" />
  if (status === 'anonymous') {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return <>{children}</>
}

export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'authenticated') return <Navigate to="/" replace />
  return <>{children}</>
}
