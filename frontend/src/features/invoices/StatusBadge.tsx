import { Badge } from '@/components/ui'
import type { InvoiceStatus } from '@/lib/types'
import { STATUS_META } from './status'

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  const meta = STATUS_META[status]
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  )
}

export function IssueCounts({ errors, warnings }: { errors: number; warnings: number }) {
  if (!errors && !warnings) return <span className="muted">None</span>
  return (
    <span style={{ display: 'inline-flex', gap: 'var(--space-1)' }}>
      {errors > 0 && (
        <Badge tone="error" title={`${errors} error(s)`}>
          {errors} {errors === 1 ? 'error' : 'errors'}
        </Badge>
      )}
      {warnings > 0 && (
        <Badge tone="warning" title={`${warnings} warning(s)`}>
          {warnings} {warnings === 1 ? 'warning' : 'warnings'}
        </Badge>
      )}
    </span>
  )
}
