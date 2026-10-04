import type { KeyboardEvent, ReactNode } from 'react'
import { ErrorState } from './States'
import styles from './Table.module.css'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: 'left' | 'right' | 'center'
  width?: number | string
  /** Numeric columns use tabular figures and right alignment. */
  numeric?: boolean
}

interface TableProps<T> {
  columns: Column<T>[]
  rows: T[] | undefined
  getRowId: (row: T) => string
  loading?: boolean
  error?: unknown
  onRetry?: () => void
  empty?: ReactNode
  onRowClick?: (row: T) => void
  rowLabel?: (row: T) => string
  skeletonRows?: number
  caption?: string
}

export function Table<T>({
  columns,
  rows,
  getRowId,
  loading,
  error,
  onRetry,
  empty,
  onRowClick,
  rowLabel,
  skeletonRows = 8,
  caption,
}: TableProps<T>) {
  const alignClass = (c: Column<T>) =>
    c.numeric || c.align === 'right' ? styles.right : c.align === 'center' ? styles.center : ''

  const onKey = (event: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (onRowClick && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault()
      onRowClick(row)
    }
  }

  let body: ReactNode
  if (error && !rows) {
    body = (
      <tr>
        <td colSpan={columns.length} className={styles.stateCell}>
          <ErrorState error={error} onRetry={onRetry} compact />
        </td>
      </tr>
    )
  } else if (loading && !rows) {
    body = Array.from({ length: skeletonRows }, (_, i) => (
      <tr key={`skeleton-${i}`} aria-hidden="true">
        {columns.map((c) => (
          <td key={c.key} className={alignClass(c)}>
            <span
              className={styles.skeleton}
              style={{ width: c.numeric ? '60%' : `${55 + ((i * 17) % 35)}%` }}
            />
          </td>
        ))}
      </tr>
    ))
  } else if (!rows || rows.length === 0) {
    body = (
      <tr>
        <td colSpan={columns.length} className={styles.stateCell}>
          {empty}
        </td>
      </tr>
    )
  } else {
    body = rows.map((row) => (
      <tr
        key={getRowId(row)}
        className={onRowClick ? styles.clickable : undefined}
        onClick={onRowClick ? () => onRowClick(row) : undefined}
        onKeyDown={onRowClick ? (e) => onKey(e, row) : undefined}
        tabIndex={onRowClick ? 0 : undefined}
        aria-label={rowLabel?.(row)}
      >
        {columns.map((c) => (
          <td key={c.key} className={`${alignClass(c)} ${c.numeric ? 'tabular' : ''}`}>
            {c.render(row)}
          </td>
        ))}
      </tr>
    ))
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table} aria-busy={loading || undefined}>
        {caption && <caption className="visually-hidden">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={alignClass(c)} style={{ width: c.width }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={loading && rows ? styles.refreshing : undefined}>{body}</tbody>
      </table>
    </div>
  )
}
