import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Page, Vendor } from '@/lib/types'

export function useVendors(params: { search?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['vendors', 'list', params],
    queryFn: ({ signal }) => api<Page<Vendor>>('/vendors', { query: params, signal }),
    placeholderData: keepPreviousData,
  })
}

export function useVendor(id: string | null) {
  return useQuery({
    queryKey: ['vendors', 'detail', id],
    queryFn: () => api<Vendor>(`/vendors/${id}`),
    enabled: Boolean(id),
  })
}

export function useUpdateVendor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; display_name: string }) =>
      api<Vendor>(`/vendors/${vars.id}`, {
        method: 'PATCH',
        body: { display_name: vars.display_name },
      }),
    onSuccess: (vendor) => {
      queryClient.setQueryData(['vendors', 'detail', vendor.id], vendor)
      void queryClient.invalidateQueries({ queryKey: ['vendors', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
