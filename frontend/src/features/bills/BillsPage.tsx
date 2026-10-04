import { useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import {
  Button,
  Card,
  EmptyState,
  Icon,
  Input,
  Pager,
  PAGE_SIZE_OPTIONS,
  Select,
} from '@/components/ui'
import { useInvoiceList } from '@/features/invoices/api'
import { InvoiceTable } from '@/features/invoices/InvoiceTable'
import { STATUS_OPTIONS } from '@/features/invoices/status'
import { useVendors } from '@/features/vendors/api'
import { intParam, useDebouncedValue, useDocumentTitle, useUrlState } from '@/lib/hooks'
import type { InvoiceStatus } from '@/lib/types'
import styles from './Filters.module.css'

const SORT_OPTIONS = [
  { value: '-created_at', label: 'Newest uploads' },
  { value: 'created_at', label: 'Oldest uploads' },
  { value: '-invoice_date', label: 'Invoice date, newest' },
  { value: 'due_date', label: 'Due date, soonest' },
  { value: '-total', label: 'Amount, highest' },
  { value: 'total', label: 'Amount, lowest' },
]

const FILTER_KEYS = ['q', 'status', 'vendor', 'from', 'to', 'min', 'max'] as const

export function BillsPage() {
  useDocumentTitle('Bills')
  const { params, update } = useUrlState()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const debouncedSearch = useDebouncedValue(search.trim())
  const [minTotal, setMinTotal] = useState(params.get('min') ?? '')
  const [maxTotal, setMaxTotal] = useState(params.get('max') ?? '')
  const debouncedMin = useDebouncedValue(minTotal.replace(/,/g, '').trim(), 400)
  const debouncedMax = useDebouncedValue(maxTotal.replace(/,/g, '').trim(), 400)

  const status = params.get('status') as InvoiceStatus | null
  const vendorId = params.get('vendor') ?? ''
  const dateFrom = params.get('from') ?? ''
  const dateTo = params.get('to') ?? ''
  const sort = params.get('sort') ?? '-created_at'
  const page = intParam(params.get('page'), 1)
  const pageSize = intParam(params.get('size'), 25, PAGE_SIZE_OPTIONS)

  const vendors = useVendors({ page_size: 100 })
  const amountError =
    (debouncedMin && Number.isNaN(Number(debouncedMin))) ||
    (debouncedMax && Number.isNaN(Number(debouncedMax)))
      ? 'Enter amounts as numbers'
      : null
  const dateError =
    dateFrom && dateTo && dateFrom > dateTo ? '"To" must be on or after "From"' : null

  const query = useInvoiceList({
    status: status ? [status] : undefined,
    vendor_id: vendorId || undefined,
    date_from: dateError ? undefined : dateFrom || undefined,
    date_to: dateError ? undefined : dateTo || undefined,
    min_total: amountError ? undefined : debouncedMin || undefined,
    max_total: amountError ? undefined : debouncedMax || undefined,
    search: debouncedSearch || undefined,
    sort,
    page,
    page_size: pageSize,
  })

  const hasFilters = FILTER_KEYS.some((k) => params.get(k))
  const clearFilters = () => {
    setSearch('')
    setMinTotal('')
    setMaxTotal('')
    update(Object.fromEntries([...FILTER_KEYS, 'page'].map((k) => [k, null])))
  }

  const total = query.data?.total ?? 0

  return (
    <>
      <PageHeader title="Bills" description="Every bill your team has uploaded, in any state." />
      <Card padded={false}>
        <div className={styles.toolbar}>
          <div className={styles.search}>
            <Input
              label="Search"
              placeholder="Vendor, invoice number, GSTIN or file name"
              value={search}
              leading={<Icon name="search" />}
              onChange={(e) => {
                setSearch(e.target.value)
                update({ q: e.target.value, page: null })
              }}
            />
          </div>
          <div className={styles.filter}>
            <Select
              label="Status"
              value={status ?? ''}
              options={[{ value: '', label: 'All statuses' }, ...STATUS_OPTIONS]}
              onChange={(e) => update({ status: e.target.value, page: null })}
            />
          </div>
          <div className={styles.filterWide}>
            <Select
              label="Vendor"
              value={vendorId}
              options={[
                { value: '', label: vendors.isLoading ? 'Loading vendors...' : 'All vendors' },
                ...(vendors.data?.items ?? []).map((v) => ({ value: v.id, label: v.display_name })),
              ]}
              onChange={(e) => update({ vendor: e.target.value, page: null })}
            />
          </div>
          <div className={styles.filterNarrow}>
            <Input
              label="Invoice date from"
              type="date"
              value={dateFrom}
              onChange={(e) => update({ from: e.target.value, page: null })}
            />
          </div>
          <div className={styles.filterNarrow}>
            <Input
              label="To"
              type="date"
              value={dateTo}
              error={dateError}
              onChange={(e) => update({ to: e.target.value, page: null })}
            />
          </div>
          <div className={styles.filterNarrow}>
            <Input
              label="Min amount (₹)"
              inputMode="decimal"
              value={minTotal}
              error={amountError}
              onChange={(e) => {
                setMinTotal(e.target.value)
                update({ min: e.target.value, page: null })
              }}
            />
          </div>
          <div className={styles.filterNarrow}>
            <Input
              label="Max amount (₹)"
              inputMode="decimal"
              value={maxTotal}
              onChange={(e) => {
                setMaxTotal(e.target.value)
                update({ max: e.target.value, page: null })
              }}
            />
          </div>
          <div className={styles.filter}>
            <Select
              label="Sort by"
              value={sort}
              options={SORT_OPTIONS}
              onChange={(e) => update({ sort: e.target.value, page: null })}
            />
          </div>
          {hasFilters && (
            <div className={styles.toolbarEnd}>
              <Button variant="ghost" icon="close" onClick={clearFilters}>
                Clear filters
              </Button>
            </div>
          )}
        </div>
        <InvoiceTable
          rows={query.data?.items}
          loading={query.isFetching}
          error={query.error}
          onRetry={() => void query.refetch()}
          from="bills"
          empty={
            hasFilters ? (
              <EmptyState
                icon="search"
                title="No bills match these filters"
                action={<Button onClick={clearFilters}>Clear filters</Button>}
              />
            ) : (
              <EmptyState
                icon="bills"
                title="No bills yet"
                description="Upload vendor invoices to see them here."
              />
            )
          }
        />
        {total > 0 && (
          <Pager
            page={query.data?.page ?? page}
            pageSize={pageSize}
            total={total}
            onPageChange={(p) => update({ page: p })}
            onPageSizeChange={(s) => update({ size: s, page: null })}
          />
        )}
      </Card>
    </>
  )
}
