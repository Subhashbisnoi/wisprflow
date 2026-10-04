import type { ReactNode } from 'react'
import styles from './Badge.module.css'

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'error'

interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  dot?: boolean
  title?: string
}

export function Badge({ tone = 'neutral', children, dot = false, title }: BadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[tone]}`} title={title}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  )
}
