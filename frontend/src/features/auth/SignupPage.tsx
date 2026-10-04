import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Input } from '@/components/ui'
import { ApiError, errorMessage } from '@/lib/api'
import { useDocumentTitle } from '@/lib/hooks'
import { isGstinShapeValid } from '@/lib/gstin'
import { useAuth, type SignupInput } from './AuthContext'
import { AuthLayout } from './AuthLayout'
import styles from './Auth.module.css'

type Errors = Partial<Record<keyof SignupInput, string>>

function validate(form: SignupInput): Errors {
  const errors: Errors = {}
  if (form.company_name.trim().length < 2) errors.company_name = 'Enter your company name.'
  if (form.full_name.trim().length < 2) errors.full_name = 'Enter your full name.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()))
    errors.email = 'Enter a valid email address.'
  if (form.password.length < 8) errors.password = 'Use at least 8 characters.'
  if (form.company_gstin && !isGstinShapeValid(form.company_gstin))
    errors.company_gstin = 'GSTIN should be 15 characters, for example 27AAPFU0939F1ZV.'
  return errors
}

export function SignupPage() {
  useDocumentTitle('Create account')
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<SignupInput>({
    company_name: '',
    company_gstin: '',
    full_name: '',
    email: '',
    password: '',
  })
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const set = (key: keyof SignupInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length) return
    setSubmitting(true)
    try {
      await signup(form)
      navigate('/', { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'validation_error') setErrors(e.fieldErrors())
      else setFormError(errorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Create your company account"
      subtitle="Set up a workspace for your finance team. You will be the administrator."
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        {formError && (
          <p className={styles.formError} role="alert">
            {formError}
          </p>
        )}
        <Input
          label="Company name"
          value={form.company_name}
          onChange={set('company_name')}
          error={errors.company_name}
          autoComplete="organization"
          autoFocus
        />
        <Input
          label="Company GSTIN (optional)"
          value={form.company_gstin}
          onChange={set('company_gstin')}
          error={errors.company_gstin}
          hint="Used to check that invoices are addressed to you and to decide CGST/SGST vs IGST."
          maxLength={15}
          className="mono"
        />
        <Input
          label="Your full name"
          value={form.full_name}
          onChange={set('full_name')}
          error={errors.full_name}
          autoComplete="name"
        />
        <Input
          label="Work email"
          type="email"
          value={form.email}
          onChange={set('email')}
          error={errors.email}
          autoComplete="email"
        />
        <Input
          label="Password"
          type="password"
          value={form.password}
          onChange={set('password')}
          error={errors.password}
          hint="At least 8 characters."
          autoComplete="new-password"
        />
        <Button type="submit" variant="primary" block loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}
