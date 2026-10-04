import { formatDate, formatINR, formatNumber } from '@/lib/format'
import type { Finding, HeaderField, InvoiceDetail, LineField, Severity } from '@/lib/types'

export type FieldKind = 'text' | 'gstin' | 'date' | 'money' | 'quantity'

export const HEADER_FIELDS: Record<HeaderField, { label: string; kind: FieldKind }> = {
  vendor_name: { label: 'Vendor name', kind: 'text' },
  vendor_gstin: { label: 'Vendor GSTIN', kind: 'gstin' },
  buyer_gstin: { label: 'Buyer GSTIN', kind: 'gstin' },
  invoice_number: { label: 'Invoice number', kind: 'text' },
  invoice_date: { label: 'Invoice date', kind: 'date' },
  due_date: { label: 'Due date', kind: 'date' },
  subtotal: { label: 'Subtotal (taxable value)', kind: 'money' },
  cgst: { label: 'CGST', kind: 'money' },
  sgst: { label: 'SGST', kind: 'money' },
  igst: { label: 'IGST', kind: 'money' },
  total: { label: 'Total', kind: 'money' },
}

export const LINE_FIELDS: Record<LineField, { label: string; kind: FieldKind }> = {
  description: { label: 'Description', kind: 'text' },
  hsn_sac: { label: 'HSN/SAC', kind: 'text' },
  quantity: { label: 'Qty', kind: 'quantity' },
  rate: { label: 'Rate', kind: 'money' },
  amount: { label: 'Amount', kind: 'money' },
}

export const FIELD_GROUPS: { title: string; fields: HeaderField[] }[] = [
  { title: 'Parties', fields: ['vendor_name', 'vendor_gstin', 'buyer_gstin'] },
  { title: 'Invoice', fields: ['invoice_number', 'invoice_date', 'due_date'] },
  { title: 'Amounts', fields: ['subtotal', 'cgst', 'sgst', 'igst', 'total'] },
]

const SEVERITY_RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 }

/** Worst finding severity per field name (header fields and `line_items.N.field`). */
export function severityByField(findings: Finding[]): Map<string, Severity> {
  const map = new Map<string, Severity>()
  for (const f of findings) {
    if (!f.field) continue
    const current = map.get(f.field)
    if (!current || SEVERITY_RANK[f.severity] < SEVERITY_RANK[current]) map.set(f.field, f.severity)
  }
  return map
}

export function confidenceLevel(confidence: number | undefined): 'high' | 'medium' | 'low' | null {
  if (confidence === undefined) return null
  if (confidence >= 0.9) return 'high'
  if (confidence >= 0.6) return 'medium'
  return 'low'
}

export function headerValue(invoice: InvoiceDetail, field: HeaderField): string | null {
  return invoice[field]
}

export const RULE_LABELS: Record<string, string> = {
  required_fields: 'Missing data',
  low_confidence: 'Low confidence',
  gstin_format: 'GSTIN',
  duplicate_invoice: 'Possible duplicate',
  line_item_arithmetic: 'Line items',
  totals: 'Totals',
  tax_rate: 'Tax rate',
  tax_type: 'Tax type',
}

export function displayValue(kind: FieldKind, value: string | null): string {
  if (value === null || value === '') return ''
  if (kind === 'money') return formatINR(value)
  if (kind === 'quantity') return formatNumber(value)
  if (kind === 'date') return formatDate(value)
  return value
}
