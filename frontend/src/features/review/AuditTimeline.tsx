import { EmptyState, ErrorState, Icon, Skeleton, type IconName } from '@/components/ui'
import { useAuditEvents } from '@/features/invoices/api'
import { formatDateTime, formatINR, pluralize } from '@/lib/format'
import type { AuditEvent } from '@/lib/types'
import { HEADER_FIELDS } from './fieldMeta'
import styles from './Review.module.css'

const MONEY_FIELDS = new Set(['subtotal', 'cgst', 'sgst', 'igst', 'total'])

function fieldLabel(name: string | null): string {
  if (!name) return 'value'
  return HEADER_FIELDS[name as keyof typeof HEADER_FIELDS]?.label ?? name.replace(/_/g, ' ')
}

function show(field: string | null, value: string | null): string {
  if (value === null || value === '') return 'empty'
  const tail = field?.split(' ').pop() ?? field
  if (field && (MONEY_FIELDS.has(field) || tail === 'amount' || tail === 'rate'))
    return formatINR(value)
  return value
}

function describe(e: AuditEvent): { icon: IconName; text: string; detail?: string } {
  const d = e.details as Record<string, string | number | undefined>
  switch (e.action) {
    case 'invoice_uploaded':
      return { icon: 'upload', text: `uploaded ${String(d.filename ?? 'the document')}` }
    case 'extraction_started':
      return { icon: 'clock', text: `started extraction (attempt ${d.attempt ?? 1})` }
    case 'extraction_completed':
      return {
        icon: 'check',
        text: `extracted ${d.line_items ?? 0} line items using ${d.method === 'vision' ? 'the scanned-image reader' : 'the PDF text layer'}`,
        detail: `${pluralize(Number(d.errors ?? 0), 'error')}, ${pluralize(Number(d.warnings ?? 0), 'warning')}${d.model ? ` / ${d.model}` : ''}`,
      }
    case 'extraction_failed':
      return { icon: 'error', text: 'could not extract this bill', detail: String(d.message ?? '') }
    case 'extraction_retried':
      return { icon: 'refresh', text: 'retried extraction' }
    case 'vendor_created':
      return { icon: 'vendors', text: `added new vendor ${e.new_value} from this invoice` }
    case 'vendor_linked':
      return {
        icon: 'vendors',
        text: e.new_value ? `linked vendor ${e.new_value}` : 'unlinked the vendor',
        detail: e.old_value ? `previously ${e.old_value}` : undefined,
      }
    case 'vendor_updated':
      return { icon: 'vendors', text: `renamed vendor from ${e.old_value} to ${e.new_value}` }
    case 'field_corrected':
      return {
        icon: 'pencil',
        text: `changed ${fieldLabel(e.field_name)} from ${show(e.field_name, e.old_value)} to ${show(e.field_name, e.new_value)}`,
      }
    case 'line_item_added':
      return { icon: 'plus', text: `added ${e.field_name}${e.new_value ? `: ${e.new_value}` : ''}` }
    case 'line_item_corrected':
      return {
        icon: 'pencil',
        text: `changed ${e.field_name} from ${show(e.field_name, e.old_value)} to ${show(e.field_name, e.new_value)}`,
      }
    case 'line_item_removed':
      return {
        icon: 'trash',
        text: `removed ${e.field_name}${e.old_value ? `: ${e.old_value}` : ''}`,
      }
    case 'invoice_approved':
      return {
        icon: 'check',
        text: 'approved the bill',
        detail: d.note ? `"${d.note}"` : undefined,
      }
    case 'invoice_rejected':
      return {
        icon: 'close',
        text: 'rejected the bill',
        detail: d.note ? `Reason: ${d.note}` : undefined,
      }
    default:
      return { icon: 'info', text: e.action.replace(/_/g, ' ') }
  }
}

export function AuditTimeline({ invoiceId }: { invoiceId: string }) {
  const { data, error, isLoading, refetch } = useAuditEvents(invoiceId, true)
  if (isLoading)
    return (
      <div className={styles.timelineSkeleton}>
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height={14} width={`${60 + i * 8}%`} />
        ))}
      </div>
    )
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} compact />
  if (!data?.items.length) return <EmptyState icon="clock" title="No activity yet" />
  return (
    <ol className={styles.timeline}>
      {data.items.map((event) => {
        const { icon, text, detail } = describe(event)
        return (
          <li key={event.id} className={styles.timelineItem}>
            <span className={`${styles.timelineIcon} ${styles[`timeline_${event.action}`] ?? ''}`}>
              <Icon name={icon} size={13} />
            </span>
            <div className={styles.timelineBody}>
              <p>
                <strong>{event.actor_name}</strong> {text}
              </p>
              {detail && <p className={styles.timelineDetail}>{detail}</p>}
              <time className={styles.timelineTime} dateTime={event.created_at}>
                {formatDateTime(event.created_at)}
              </time>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
