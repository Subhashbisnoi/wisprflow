import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import styles from './Field.module.css'

interface FieldShellProps {
  label?: string
  hint?: ReactNode
  error?: string | null
  id: string
  children: ReactNode
  hideLabel?: boolean
}

function FieldShell({ label, hint, error, id, children, hideLabel }: FieldShellProps) {
  return (
    <div className={styles.field}>
      {label && (
        <label htmlFor={id} className={hideLabel ? 'visually-hidden' : styles.label}>
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className={styles.hint}>
          {hint}
        </p>
      ) : null}
    </div>
  )
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: ReactNode
  error?: string | null
  hideLabel?: boolean
  leading?: ReactNode
}

export function Input({
  label,
  hint,
  error,
  hideLabel,
  leading,
  id,
  className,
  ...rest
}: InputProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <FieldShell label={label} hint={hint} error={error} id={inputId} hideLabel={hideLabel}>
      <div className={`${styles.control} ${error ? styles.invalid : ''} ${className ?? ''}`}>
        {leading && <span className={styles.leading}>{leading}</span>}
        <input
          id={inputId}
          className={styles.input}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          {...rest}
        />
      </div>
    </FieldShell>
  )
}

export interface SelectOption {
  value: string
  label: string
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  hint?: ReactNode
  error?: string | null
  hideLabel?: boolean
  options: SelectOption[]
}

export function Select({
  label,
  hint,
  error,
  hideLabel,
  options,
  id,
  className,
  ...rest
}: SelectProps) {
  const autoId = useId()
  const selectId = id ?? autoId
  return (
    <FieldShell label={label} hint={hint} error={error} id={selectId} hideLabel={hideLabel}>
      <div
        className={`${styles.control} ${styles.selectControl} ${error ? styles.invalid : ''} ${className ?? ''}`}
      >
        <select
          id={selectId}
          className={styles.select}
          aria-invalid={error ? true : undefined}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <svg
          className={styles.chevron}
          viewBox="0 0 24 24"
          width="14"
          height="14"
          aria-hidden="true"
        >
          <path
            d="M6 9l6 6 6-6"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </div>
    </FieldShell>
  )
}
