import styles from './Layout.module.css'

export function Logo({ inverted = false }: { inverted?: boolean }) {
  return (
    <span className={`${styles.logo} ${inverted ? styles.logoInverted : ''}`}>
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" className={styles.logoMark} />
        <path d="M10 8v16h12" className={styles.logoStroke} />
        <path d="M15 18h7" className={styles.logoAccent} />
      </svg>
      <span className={styles.logoText}>Ledgerline</span>
    </span>
  )
}
