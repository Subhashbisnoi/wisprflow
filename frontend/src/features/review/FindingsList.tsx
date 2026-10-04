import { Icon, type IconName } from '@/components/ui'
import type { Finding, Severity } from '@/lib/types'
import { RULE_LABELS } from './fieldMeta'
import styles from './Review.module.css'

const ICON: Record<Severity, IconName> = { error: 'error', warning: 'alert', info: 'info' }
const LABEL: Record<Severity, string> = { error: 'Error', warning: 'Warning', info: 'Info' }

function focusField(field: string | null) {
  if (!field) return
  const id = field.startsWith('line_items') ? 'line-items' : `field-${field}`
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.querySelector<HTMLElement>('button, input')?.focus({ preventScroll: true })
}

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return (
      <div className={styles.allClear}>
        <Icon name="check" size={16} />
        <span>All checks passed. Verify the fields against the document, then approve.</span>
      </div>
    )
  }
  return (
    <ul className={styles.findings}>
      {findings.map((f) => (
        <li key={f.id} className={`${styles.finding} ${styles[`finding_${f.severity}`]}`}>
          <span className={styles.findingIcon}>
            <Icon name={ICON[f.severity]} size={16} label={LABEL[f.severity]} />
          </span>
          <div className={styles.findingBody}>
            <p className={styles.findingTitle}>
              {RULE_LABELS[f.rule_code] ?? f.rule_code}
              <span className={styles.findingSeverity}>{LABEL[f.severity]}</span>
            </p>
            <p className={styles.findingMessage}>{f.message}</p>
          </div>
          {f.field && (
            <button
              type="button"
              className={styles.findingJump}
              onClick={() => focusField(f.field)}
            >
              Go to field
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
