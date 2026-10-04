import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Input } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { useDocumentTitle } from '@/lib/hooks'
import { useAuth } from './AuthContext'
import { AuthLayout } from './AuthLayout'
import styles from './Auth.module.css'

// Seeded by `make seed` (backend/scripts/seed_demo.py).
const DEMO_EMAIL = 'demo@ledgerline.in'
const DEMO_PASSWORD = 'Demo@12345'

function safeNext(next: string | null): string {
  // Only allow in-app relative paths to avoid open redirects.
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
}

export function LoginPage() {
  useDocumentTitle('Sign in')
  const { login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const reason = params.get('reason')

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(safeNext(params.get('next')), { replace: true })
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Welcome back. Sign in to your finance workspace."
      footer={
        <>
          New to Ledgerline? <Link to="/signup">Create a company account</Link>
        </>
      }
    >
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        {reason === 'expired' && (
          <p className={styles.notice} role="status">
            Your session expired. Please sign in again.
          </p>
        )}
        {reason === 'invalid' && (
          <p className={styles.notice} role="status">
            Please sign in to continue.
          </p>
        )}
        <div className={styles.demo}>
          <div>
            <p className={styles.demoTitle}>Demo account</p>
            <p className={styles.demoCreds}>
              <span className="mono">{DEMO_EMAIL}</span> /{' '}
              <span className="mono">{DEMO_PASSWORD}</span>
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => {
              setEmail(DEMO_EMAIL)
              setPassword(DEMO_PASSWORD)
            }}
          >
            Use demo account
          </Button>
        </div>
        {error && (
          <p className={styles.formError} role="alert">
            {error}
          </p>
        )}
        <Input
          label="Work email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button
          type="submit"
          variant="primary"
          block
          loading={submitting}
          disabled={!email || !password}
        >
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
