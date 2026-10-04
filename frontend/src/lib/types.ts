// Mirrors the backend Pydantic schemas. Money and quantities are strings (D-046).

export type UUID = string
export type Money = string

export type InvoiceStatus =
  'queued' | 'processing' | 'needs_review' | 'approved' | 'rejected' | 'failed'

export type Severity = 'error' | 'warning' | 'info'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface User {
  id: UUID
  email: string
  full_name: string
  role: 'admin' | 'reviewer'
}

export interface Company {
  id: UUID
  name: string
  gstin: string | null
  state_code: string | null
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: User
  company: Company
}

export interface VendorRef {
  id: UUID
  display_name: string
  legal_name: string
  gstin: string
}

export interface InvoiceSummary {
  id: UUID
  status: InvoiceStatus
  original_filename: string
  vendor: VendorRef | null
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  total: Money | null
  error_count: number
  warning_count: number
  error_message: string | null
  version: number
  created_at: string
}

export interface LineItem {
  id: UUID
  position: number
  description: string | null
  hsn_sac: string | null
  quantity: string | null
  rate: Money | null
  amount: Money | null
  confidence: Record<string, number>
}

export interface Finding {
  id: UUID
  rule_code: string
  severity: Severity
  field: string | null
  message: string
}

export interface InvoiceDetail extends InvoiceSummary {
  vendor_gstin: string | null
  buyer_gstin: string | null
  currency: string
  subtotal: Money | null
  cgst: Money | null
  sgst: Money | null
  igst: Money | null
  field_confidence: Record<string, number>
  line_items: LineItem[]
  findings: Finding[]
  content_type: string
  file_size_bytes: number
  page_count: number | null
  pages_processed: number | null
  extraction_method: 'text_layer' | 'vision' | null
  extraction_model: string | null
  extraction_attempts: number
  uploaded_by_name: string
  reviewed_by_name: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  review_comment: string | null
  updated_at: string
}

export type HeaderField =
  | 'vendor_name'
  | 'vendor_gstin'
  | 'buyer_gstin'
  | 'invoice_number'
  | 'invoice_date'
  | 'due_date'
  | 'subtotal'
  | 'cgst'
  | 'sgst'
  | 'igst'
  | 'total'

export type LineField = 'description' | 'hsn_sac' | 'quantity' | 'rate' | 'amount'

export interface UploadResult {
  filename: string
  status: 'accepted' | 'rejected'
  invoice: InvoiceSummary | null
  error: { code: string; message: string } | null
}

export interface UploadResponse {
  results: UploadResult[]
  accepted: number
  rejected: number
}

export interface AuditEvent {
  id: UUID
  action: string
  entity_type: string
  entity_id: UUID
  actor_user_id: UUID | null
  actor_name: string
  field_name: string | null
  old_value: string | null
  new_value: string | null
  details: Record<string, unknown>
  created_at: string
}

export interface Vendor {
  id: UUID
  gstin: string
  legal_name: string
  display_name: string
  state_code: string
  state_name: string
  bill_count: number
  approved_spend: Money
  pending_amount: Money
  created_at: string
}

export interface DashboardSummary {
  as_of: string
  kpis: {
    total_this_month: Money
    bills_this_month: number
    pending_amount: Money
    needs_review_count: number
    approval_rate: number | null
    approved_this_month: number
    rejected_this_month: number
    failed_count: number
    processing_count: number
  }
  monthly_spend: { month: string; approved: Money; pending: Money }[]
  top_vendors: { vendor_id: UUID; display_name: string; amount: Money; bill_count: number }[]
  status_breakdown: { status: InvoiceStatus; count: number; amount: Money }[]
  total_bills: number
}
