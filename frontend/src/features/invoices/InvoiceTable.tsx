import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, type Column } from '@/components/ui'
import { formatDate, formatINR, formatRelative } from '@/lib/format'
import type { InvoiceSummary } from '@/lib/types'
import { vendorLabel } from './status'
import { IssueCounts, StatusBadge } from './StatusBadge'
import styles from './InvoiceTable.module.css'

const columns: Column<InvoiceSummary>[] = [
  {
    key: 'vendor',
    header: 'Vendor',
    render: (inv) => (
      <div className={styles.vendorCell}>
        <span className={styles.vendorName}>{vendorLabel(inv)}</span>
        <span className={styles.filename}>{inv.original_filename}</span>
      </div>
    ),
  },
  {
    key: 'number',
    header: 'Invoice no.',
    render: (inv) => <span className={`mono ${styles.nowrap}`}>{inv.invoice_number ?? '-'}</span>,
  },
  {
    key: 'date',
    header: 'Invoice date',
    render: (inv) => formatDate(inv.invoice_date),
    width: 120,
  },
  { key: 'due', header: 'Due date', render: (inv) => formatDate(inv.due_date), width: 120 },
  {
    key: 'total',
    header: 'Amount',
    numeric: true,
    render: (inv) => formatINR(inv.total),
    width: 140,
  },
  {
    key: 'issues',
    header: 'Issues',
    render: (inv) =>
      inv.status === 'failed' ? (
        <span className={styles.failed}>Extraction failed</span>
      ) : inv.status === 'queued' || inv.status === 'processing' ? (
        <span className="muted">-</span>
      ) : (
        <IssueCounts errors={inv.error_count} warnings={inv.warning_count} />
      ),
    width: 170,
  },
  {
    key: 'status',
    header: 'Status',
    render: (inv) => <StatusBadge status={inv.status} />,
    width: 130,
  },
  {
    key: 'uploaded',
    header: 'Uploaded',
    render: (inv) => <span className="muted">{formatRelative(inv.created_at)}</span>,
    width: 110,
  },
]

export function InvoiceTable({
  rows,
  loading,
  error,
  onRetry,
  empty,
  from,
}: {
  rows: InvoiceSummary[] | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
  empty: ReactNode
  from: 'review' | 'bills'
}) {
  const navigate = useNavigate()
  return (
    <Table
      columns={columns}
      rows={rows}
      getRowId={(inv) => inv.id}
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={empty}
      onRowClick={(inv) => navigate(`/bills/${inv.id}?from=${from}`)}
      rowLabel={(inv) =>
        `Open bill ${inv.invoice_number ?? inv.original_filename} from ${vendorLabel(inv)}`
      }
      caption="Bills"
    />
  )
}
