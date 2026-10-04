import type { BadgeTone } from '@/components/ui'
import type { InvoiceStatus, InvoiceSummary } from '@/lib/types'

export const STATUS_META: Record<InvoiceStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  processing: { label: 'Extracting', tone: 'neutral' },
  needs_review: { label: 'Needs review', tone: 'info' },
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'error' },
  failed: { label: 'Failed', tone: 'error' },
}

export const STATUS_OPTIONS = (Object.keys(STATUS_META) as InvoiceStatus[]).map((s) => ({
  value: s,
  label: STATUS_META[s].label,
}))

export function vendorLabel(inv: InvoiceSummary): string {
  return inv.vendor?.display_name ?? inv.vendor_name ?? 'Unknown vendor'
}
