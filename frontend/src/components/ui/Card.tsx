import type { HTMLAttributes, ReactNode } from 'react'
import styles from './Card.module.css'

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  padded?: boolean
  children?: ReactNode
}

export function Card({
  title,
  subtitle,
  actions,
  padded = true,
  children,
  className,
  ...rest
}: CardProps) {
  return (
    <section className={`${styles.card} ${className ?? ''}`} {...rest}>
      {(title || actions) && (
        <header className={styles.header}>
          <div className={styles.titles}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      <div className={padded ? styles.body : undefined}>{children}</div>
    </section>
  )
}
