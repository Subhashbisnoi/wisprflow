import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Icon,
  Skeleton,
  type IconName,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatDate, formatINR, formatPercent, pluralize } from '@/lib/format'
import { useDocumentTitle } from '@/lib/hooks'
import type { DashboardSummary } from '@/lib/types'
import { SpendChart } from './SpendChart'
import styles from './Dashboard.module.css'

function KpiCard({
  label,
  value,
  detail,
  icon,
  to,
}: {
  label: string
  value: ReactNode
  detail: ReactNode
  icon: IconName
  to?: string
}) {
  const body = (
    <>
      <div className={styles.kpiTop}>
        <span className={styles.kpiLabel}>{label}</span>
        <span className={styles.kpiIcon}>
          <Icon name={icon} size={16} />
        </span>
      </div>
      <p className={`${styles.kpiValue} tabular`}>{value}</p>
      <p className={styles.kpiDetail}>{detail}</p>
    </>
  )
  return to ? (
    <Link to={to} className={`${styles.kpi} ${styles.kpiLink}`}>
      {body}
    </Link>
  ) : (
    <div className={styles.kpi}>{body}</div>
  )
}

function KpiSkeleton() {
  return (
    <div className={styles.kpi} aria-hidden="true">
      <Skeleton width="50%" height={12} />
      <div style={{ height: 'var(--space-3)' }} />
      <Skeleton width="70%" height={26} />
      <div style={{ height: 'var(--space-2)' }} />
      <Skeleton width="40%" height={10} />
    </div>
  )
}

export function DashboardPage() {
  useDocumentTitle('Dashboard')
  const navigate = useNavigate()
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<DashboardSummary>('/dashboard/summary'),
    refetchInterval: 60_000,
  })

  const month = data
    ? new Date(`${data.as_of}T00:00:00`).toLocaleString('en-IN', { month: 'long', year: 'numeric' })
    : ''

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Card>
          <ErrorState error={error} onRetry={() => void refetch()} />
        </Card>
      </>
    )
  }

  if (data && data.total_bills === 0) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Card>
          <EmptyState
            icon="upload"
            title="Upload your first bills"
            description="Once vendor invoices are uploaded and reviewed, spend and approval figures appear here."
            action={
              <Button variant="primary" icon="upload" onClick={() => navigate('/upload')}>
                Upload bills
              </Button>
            }
          />
        </Card>
      </>
    )
  }

  const k = data?.kpis
  return (
    <>
      <PageHeader
        title="Dashboard"
        description={
          data
            ? `Accounts payable overview for ${month}. Figures as of ${formatDate(data.as_of)}.`
            : 'Loading overview'
        }
        actions={
          <Link to="/upload">
            <Button variant="primary" icon="upload">
              Upload bills
            </Button>
          </Link>
        }
      />

      {k && (k.failed_count > 0 || k.processing_count > 0) && (
        <div className={styles.notice} role="status">
          <Icon name={k.failed_count ? 'alert' : 'clock'} />
          <span>
            {k.processing_count > 0 && `${pluralize(k.processing_count, 'bill')} being extracted. `}
            {k.failed_count > 0 &&
              `${pluralize(k.failed_count, 'bill')} could not be read and need a retry.`}
          </span>
          {k.failed_count > 0 && <Link to="/review?filter=failed">View failed bills</Link>}
        </div>
      )}

      <section className={styles.kpis} aria-label="Key figures">
        {!k ? (
          <>
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
            <KpiSkeleton />
          </>
        ) : (
          <>
            <KpiCard
              label="Total this month"
              icon="bills"
              value={formatINR(k.total_this_month)}
              detail={`${pluralize(k.bills_this_month, 'bill')} dated ${month}, excluding rejected`}
              to="/bills"
            />
            <KpiCard
              label="Pending amount"
              icon="clock"
              value={formatINR(k.pending_amount)}
              detail="Waiting for review or approval"
              to="/bills?status=needs_review"
            />
            <KpiCard
              label="Bills needing review"
              icon="inbox"
              value={k.needs_review_count.toLocaleString('en-IN')}
              detail={k.needs_review_count ? 'Open the review queue' : 'All caught up'}
              to="/review"
            />
            <KpiCard
              label="Approval rate"
              icon="check"
              value={formatPercent(k.approval_rate)}
              detail={
                k.approval_rate === null
                  ? 'No decisions yet this month'
                  : `${k.approved_this_month} approved, ${k.rejected_this_month} rejected this month`
              }
            />
          </>
        )}
      </section>

      <div className={styles.grid}>
        <Card title="Monthly spend" subtitle="Bill totals by invoice month, last 6 months">
          {isLoading || !data ? (
            <Skeleton height={260} />
          ) : (
            <SpendChart data={data.monthly_spend} />
          )}
        </Card>
        <Card title="Top vendors" subtitle="By billed amount, last 6 months" padded={false}>
          {isLoading || !data ? (
            <div className={styles.listSkeleton}>
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} height={14} />
              ))}
            </div>
          ) : data.top_vendors.length === 0 ? (
            <EmptyState icon="vendors" title="No vendor spend yet" />
          ) : (
            <ol className={styles.vendorList}>
              {data.top_vendors.map((v, i) => {
                const max = Number(data.top_vendors[0]?.amount ?? 1) || 1
                return (
                  <li key={v.vendor_id}>
                    <Link to={`/bills?vendor=${v.vendor_id}`} className={styles.vendorRow}>
                      <span className={styles.vendorRank}>{i + 1}</span>
                      <span className={styles.vendorMain}>
                        <span className={styles.vendorName}>{v.display_name}</span>
                        <span className={styles.vendorBar} aria-hidden="true">
                          <span
                            style={{ width: `${Math.max(3, (Number(v.amount) / max) * 100)}%` }}
                          />
                        </span>
                      </span>
                      <span className={styles.vendorAmount}>
                        <span className="tabular">{formatINR(v.amount)}</span>
                        <span className={styles.vendorBills}>
                          {pluralize(v.bill_count, 'bill')}
                        </span>
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ol>
          )}
        </Card>
      </div>
    </>
  )
}
