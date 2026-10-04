import type { ReactNode } from 'react'
import { ApiError, errorMessage } from '@/lib/api'
import { Button } from './Button'
import { Icon, type IconName } from './Icon'
import { Spinner } from './Spinner'
import styles from './States.module.css'

interface EmptyStateProps {
  icon?: IconName
  title: string
  description?: ReactNode
  action?: ReactNode
}

export function EmptyState({ icon = 'inbox', title, description, action }: EmptyStateProps) {
  return (
    <div className={styles.state}>
      <span className={styles.iconWrap}>
        <Icon name={icon} size={22} />
      </span>
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: unknown
  onRetry?: () => void
  compact?: boolean
}) {
  const requestId = error instanceof ApiError ? error.requestId : null
  return (
    <div className={`${styles.state} ${compact ? styles.compact : ''}`} role="alert">
      <span className={`${styles.iconWrap} ${styles.errorIcon}`}>
        <Icon name="error" size={22} />
      </span>
      <p className={styles.title}>Could not load this data</p>
      <p className={styles.description}>{errorMessage(error)}</p>
      {requestId && <p className={styles.reference}>Reference: {requestId}</p>}
      {onRetry && (
        <div className={styles.action}>
          <Button icon="refresh" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  )
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className={styles.state}>
      <Spinner size={22} label={label} />
      <p className={styles.description}>{label}...</p>
    </div>
  )
}

export function Skeleton({
  width = '100%',
  height = 12,
}: {
  width?: number | string
  height?: number
}) {
  return <span className={styles.skeleton} style={{ width, height }} aria-hidden="true" />
}
