import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  AuditEvent,
  HeaderField,
  InvoiceDetail,
  InvoiceStatus,
  InvoiceSummary,
  LineField,
  Page,
} from '@/lib/types'

export interface InvoiceListParams {
  status?: InvoiceStatus[]
  vendor_id?: string
  date_from?: string
  date_to?: string
  min_total?: string
  max_total?: string
  search?: string
  ids?: string[]
  sort?: string
  page?: number
  page_size?: number
}

export const invoiceKeys = {
  all: ['invoices'] as const,
  list: (params: InvoiceListParams) => ['invoices', 'list', params] as const,
  detail: (id: string) => ['invoices', 'detail', id] as const,
  audit: (id: string) => ['invoices', 'audit', id] as const,
}

const IN_FLIGHT: InvoiceStatus[] = ['queued', 'processing']

export function useInvoiceList(params: InvoiceListParams, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: invoiceKeys.list(params),
    enabled: options.enabled ?? true,
    queryFn: ({ signal }) =>
      api<Page<InvoiceSummary>>('/invoices', { query: { ...params }, signal }),
    placeholderData: keepPreviousData,
    // Keep polling while anything on screen is still being extracted.
    refetchInterval: (query) =>
      query.state.data?.items.some((i) => IN_FLIGHT.includes(i.status)) ? 2000 : false,
  })
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: invoiceKeys.detail(id ?? ''),
    queryFn: ({ signal }) => api<InvoiceDetail>(`/invoices/${id}`, { signal }),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data && IN_FLIGHT.includes(query.state.data.status) ? 2000 : false,
  })
}

export function useAuditEvents(id: string, enabled: boolean) {
  return useQuery({
    queryKey: invoiceKeys.audit(id),
    queryFn: () =>
      api<Page<AuditEvent>>(`/invoices/${id}/audit-events`, { query: { page_size: 100 } }),
    enabled,
  })
}

/** Store a fresh detail response and invalidate everything derived from it. */
function useApplyDetail() {
  const queryClient = useQueryClient()
  return (detail: InvoiceDetail) => {
    queryClient.setQueryData(invoiceKeys.detail(detail.id), detail)
    void queryClient.invalidateQueries({ queryKey: invoiceKeys.audit(detail.id) })
    void queryClient.invalidateQueries({ queryKey: ['invoices', 'list'] })
    void queryClient.invalidateQueries({ queryKey: ['invoices', 'review-count'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['vendors'] })
  }
}

export function useCorrectFields(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: {
      version: number
      changes: { field: HeaderField; value: string | null }[]
    }) => api<InvoiceDetail>(`/invoices/${id}/fields`, { method: 'PATCH', body: vars }),
    onSuccess: apply,
  })
}

export function useCorrectLineItem(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: {
      itemId: string
      version: number
      changes: { field: LineField; value: string | null }[]
    }) =>
      api<InvoiceDetail>(`/invoices/${id}/line-items/${vars.itemId}`, {
        method: 'PATCH',
        body: { version: vars.version, changes: vars.changes },
      }),
    onSuccess: apply,
  })
}

export function useAddLineItem(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: { version: number } & Partial<Record<LineField, string>>) =>
      api<InvoiceDetail>(`/invoices/${id}/line-items`, { method: 'POST', body: vars }),
    onSuccess: apply,
  })
}

export function useRemoveLineItem(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: { itemId: string; version: number }) =>
      api<InvoiceDetail>(`/invoices/${id}/line-items/${vars.itemId}`, {
        method: 'DELETE',
        query: { version: vars.version },
      }),
    onSuccess: apply,
  })
}

export function useApprove(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: { version: number; comment?: string }) =>
      api<InvoiceDetail>(`/invoices/${id}/approve`, { method: 'POST', body: vars }),
    onSuccess: apply,
  })
}

export function useReject(id: string) {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (vars: { version: number; reason: string }) =>
      api<InvoiceDetail>(`/invoices/${id}/reject`, { method: 'POST', body: vars }),
    onSuccess: apply,
  })
}

export function useRetryExtraction() {
  const apply = useApplyDetail()
  return useMutation({
    mutationFn: (id: string) => api<InvoiceDetail>(`/invoices/${id}/retry`, { method: 'POST' }),
    onSuccess: apply,
  })
}

/** Next bill waiting for review (oldest first), skipping the one just decided. */
export async function fetchNextInReview(excludeId: string): Promise<string | null> {
  const page = await api<Page<InvoiceSummary>>('/invoices', {
    query: { status: ['needs_review'], sort: 'created_at', page_size: 2 },
  })
  return page.items.find((i) => i.id !== excludeId)?.id ?? null
}
