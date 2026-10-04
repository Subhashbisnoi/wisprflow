import { useQuery } from '@tanstack/react-query'
import { Suspense, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Icon, LoadingState, type IconName } from '@/components/ui'
import { useAuth } from '@/features/auth/AuthContext'
import { api } from '@/lib/api'
import type { Page, InvoiceSummary } from '@/lib/types'
import { Logo } from './Logo'
import styles from './Layout.module.css'

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/upload', label: 'Upload', icon: 'upload' },
  { to: '/review', label: 'Review queue', icon: 'inbox' },
  { to: '/bills', label: 'Bills', icon: 'bills' },
  { to: '/vendors', label: 'Vendors', icon: 'vendors' },
]

function useReviewCount(): number | undefined {
  const { data } = useQuery({
    queryKey: ['invoices', 'review-count'],
    queryFn: () =>
      api<Page<InvoiceSummary>>('/invoices', { query: { status: ['needs_review'], page_size: 1 } }),
    refetchInterval: 30_000,
  })
  return data?.total
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!user) return null
  return (
    <div className={styles.userMenu} ref={ref}>
      <button
        type="button"
        className={styles.userButton}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className={styles.avatar} aria-hidden="true">
          {initials(user.full_name)}
        </span>
        <span className={styles.userName}>{user.full_name}</span>
        <Icon name="chevronDown" size={14} />
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          <div className={styles.menuHeader}>
            <p className={styles.menuName}>{user.full_name}</p>
            <p className={styles.menuEmail}>{user.email}</p>
            <p className={styles.menuRole}>
              {user.role === 'admin' ? 'Administrator' : 'Reviewer'}
            </p>
          </div>
          <button type="button" role="menuitem" className={styles.menuItem} onClick={logout}>
            <Icon name="logout" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export function AppShell() {
  const { company } = useAuth()
  const reviewCount = useReviewCount()
  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarBrand}>
          <Logo inverted />
        </div>
        <nav aria-label="Main" className={styles.nav}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navActive : ''}`}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
              {item.to === '/review' && reviewCount ? (
                <span
                  className={`${styles.navCount} tabular`}
                  aria-label={`${reviewCount} bills need review`}
                >
                  {reviewCount}
                </span>
              ) : null}
            </NavLink>
          ))}
        </nav>
        <p className={styles.sidebarFooter}>MVP 0.1</p>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.company}>
            <span className={styles.companyName}>{company?.name}</span>
            {company?.gstin && (
              <span className={`${styles.companyGstin} mono`}>GSTIN {company.gstin}</span>
            )}
          </div>
          <UserMenu />
        </header>
        <main id="main" className={styles.content} tabIndex={-1}>
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
