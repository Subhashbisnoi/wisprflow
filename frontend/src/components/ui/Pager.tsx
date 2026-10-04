import { useId } from 'react'
import { PAGE_SIZE_OPTIONS } from './constants'
import { Icon } from './Icon'
import styles from './Pager.module.css'

interface PagerProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

export function Pager({ page, pageSize, total, onPageChange, onPageSizeChange }: PagerProps) {
  const id = useId()
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav className={styles.pager} aria-label="Pagination">
      <div className={styles.size}>
        <label htmlFor={id}>Rows per page</label>
        <select
          id={id}
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className={styles.select}
        >
          {PAGE_SIZE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <p className={`${styles.range} tabular`} aria-live="polite">
        {from.toLocaleString('en-IN')}-{to.toLocaleString('en-IN')} of{' '}
        {total.toLocaleString('en-IN')}
      </p>
      <div className={styles.buttons}>
        <button
          type="button"
          className={styles.nav}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <Icon name="chevronLeft" />
        </button>
        <span className={`${styles.pageLabel} tabular`}>
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className={styles.nav}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          <Icon name="chevronRight" />
        </button>
      </div>
    </nav>
  )
}
