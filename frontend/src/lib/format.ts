// Formatting helpers. Indian rupee with lakh grouping via Intl 'en-IN' (D-084).

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const inrCompact = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  notation: 'compact',
  maximumFractionDigits: 1,
})

const plain = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 })

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

/** 1234567.5 -> "₹12,34,567.50" */
export function formatINR(value: string | number | null | undefined, fallback = '-'): string {
  const n = toNumber(value)
  return n === null ? fallback : inr.format(n)
}

/** 1234567 -> "₹12.3L" (axis labels). */
export function formatINRCompact(value: string | number | null | undefined): string {
  const n = toNumber(value)
  return n === null ? '-' : inrCompact.format(n)
}

export function formatNumber(value: string | number | null | undefined, fallback = '-'): string {
  const n = toNumber(value)
  return n === null ? fallback : plain.format(n)
}

const dateFmt = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})
const dateTimeFmt = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const monthFmt = new Intl.DateTimeFormat('en-IN', { month: 'short', year: '2-digit' })

/** Parse a backend date ("2026-10-04") as a local calendar date, not UTC midnight. */
function parseDate(value: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
}

export function formatDate(value: string | null | undefined, fallback = '-'): string {
  return value ? dateFmt.format(parseDate(value)) : fallback
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTimeFmt.format(new Date(value)) : '-'
}

export function formatMonth(value: string): string {
  return monthFmt.format(parseDate(value))
}

export function formatRelative(value: string, now: Date = new Date()): string {
  const seconds = Math.round((now.getTime() - new Date(value).getTime()) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} d ago`
  return formatDate(value)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatPercent(fraction: number | null | undefined): string {
  return fraction === null || fraction === undefined ? '-' : `${Math.round(fraction * 100)}%`
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}
