import type { ReactNode } from 'react'
import { Logo } from '@/app/layout/Logo'
import styles from './Auth.module.css'

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <div className={styles.brand}>
          <Logo />
        </div>
        <div className={styles.card}>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>{subtitle}</p>
          {children}
        </div>
        <p className={styles.footer}>{footer}</p>
      </div>
      <aside className={styles.aside} aria-hidden="true">
        <div className={styles.asideInner}>
          <p className={styles.asideEyebrow}>Accounts payable for Indian businesses</p>
          <p className={styles.asideHeadline}>
            Every vendor bill read, checked and approved with a full audit trail.
          </p>
          <ul className={styles.asideList}>
            <li>GSTIN, tax-rate and CGST/SGST/IGST checks on every invoice</li>
            <li>Duplicate detection before anything is approved</li>
            <li>Who changed what, from which value, and when</li>
          </ul>
        </div>
      </aside>
    </main>
  )
}
