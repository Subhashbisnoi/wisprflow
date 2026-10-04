import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { Icon, Spinner } from '@/components/ui'
import { ApiError, errorMessage } from '@/lib/api'
import type { Severity } from '@/lib/types'
import { displayValue, type FieldKind } from './fieldMeta'
import styles from './Review.module.css'

function clientCheck(kind: FieldKind, raw: string): string | null {
  const value = raw.trim()
  if (!value) return null
  if ((kind === 'money' || kind === 'quantity') && !/^\d[\d,]*(\.\d+)?$/.test(value))
    return 'Enter a number, for example 12500.50.'
  if (kind === 'gstin' && value.replace(/\s/g, '').length > 15) return 'A GSTIN has 15 characters.'
  return null
}

interface EditableValueProps {
  kind: FieldKind
  value: string | null
  label: string
  editable: boolean
  onSave: (value: string | null) => Promise<unknown>
  severity?: Severity
  /** compact: used inside table cells */
  compact?: boolean
  placeholder?: string
}

/** Click (or Enter) to edit in place; Enter saves, Escape cancels (user flow 4). */
export function EditableValue({
  kind,
  value,
  label,
  editable,
  onSave,
  severity,
  compact = false,
  placeholder = 'Not found',
}: EditableValueProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const errorId = useId()

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const start = () => {
    if (!editable) return
    setDraft(value ?? '')
    setError(null)
    setEditing(true)
  }

  const cancel = () => {
    setEditing(false)
    setError(null)
  }

  const save = async () => {
    const trimmed = draft.trim()
    if (trimmed === (value ?? '')) {
      cancel()
      return
    }
    const problem = clientCheck(kind, trimmed)
    if (problem) {
      setError(problem)
      return
    }
    setSaving(true)
    try {
      await onSave(trimmed === '' ? null : trimmed)
      setEditing(false)
    } catch (e) {
      // Conflicts are handled by the page (reload + toast); show field-level problems here.
      if (e instanceof ApiError && e.code === 'validation_error') {
        setError(Object.values(e.fieldErrors())[0] ?? e.message)
      } else if (
        e instanceof ApiError &&
        (e.code === 'version_conflict' || e.code === 'invalid_state')
      ) {
        setEditing(false)
      } else {
        setError(errorMessage(e))
      }
    } finally {
      setSaving(false)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      void save()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      cancel()
    }
  }

  if (editing) {
    return (
      <div className={styles.editor}>
        <div className={styles.editorRow}>
          <input
            ref={inputRef}
            className={`${styles.editorInput} ${error ? styles.editorInvalid : ''} ${kind === 'gstin' ? 'mono' : ''} ${
              kind === 'money' || kind === 'quantity' ? 'tabular' : ''
            }`}
            type={kind === 'date' ? 'date' : 'text'}
            inputMode={kind === 'money' || kind === 'quantity' ? 'decimal' : undefined}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label={label}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            disabled={saving}
          />
          <button
            type="button"
            className={styles.editorButton}
            onClick={() => void save()}
            disabled={saving}
            aria-label={`Save ${label}`}
          >
            {saving ? <Spinner size={12} /> : <Icon name="check" size={14} />}
          </button>
          <button
            type="button"
            className={styles.editorButton}
            onClick={cancel}
            disabled={saving}
            aria-label="Cancel"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
        {error && (
          <p id={errorId} className={styles.editorError} role="alert">
            {error}
          </p>
        )}
      </div>
    )
  }

  const shown = displayValue(kind, value)
  const classes = [
    styles.valueButton,
    compact ? styles.valueCompact : '',
    severity ? styles[`mark_${severity}`] : '',
    kind === 'money' || kind === 'quantity' ? styles.valueNumeric : '',
  ].join(' ')

  if (!editable) {
    return (
      <span className={classes} data-readonly="true">
        <span className={`${shown ? '' : styles.placeholder} ${kind === 'gstin' ? 'mono' : ''}`}>
          {shown || placeholder}
        </span>
      </span>
    )
  }

  return (
    <button
      type="button"
      className={classes}
      onClick={start}
      aria-label={`${label}: ${shown || placeholder}. Edit`}
    >
      <span className={`${shown ? '' : styles.placeholder} ${kind === 'gstin' ? 'mono' : ''}`}>
        {shown || placeholder}
      </span>
      <span className={styles.pencil}>
        <Icon name="pencil" size={13} />
      </span>
    </button>
  )
}
