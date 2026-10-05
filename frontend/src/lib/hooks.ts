import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(id)
  }, [value, delayMs])
  return debounced
}

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} | Ledgerline` : 'Ledgerline'
  }, [title])
}

/** Parse a positive integer URL param, falling back when missing or not allowed. */
export function intParam(value: string | null, fallback: number, allowed?: number[]): number {
  const n = Number(value)
  if (!Number.isInteger(n) || n < 1) return fallback
  return allowed && !allowed.includes(n) ? fallback : n
}

/** Read and update URL search params as page state (filters survive reload and back). */
export function useUrlState() {
  const [params, setParams] = useSearchParams()
  const update = (changes: Record<string, string | number | null | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === undefined || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    setParams(next, { replace: true })
  }
  return { params, update }
}

/** Current time that re-renders the caller every `intervalMs` (keeps render pure). */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}
