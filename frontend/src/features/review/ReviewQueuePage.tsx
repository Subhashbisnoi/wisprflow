import { useState } from 'react'
import { Link } from 'react-router-dom'
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
import styles from '@/features/bills/Filters.module.css'
import { useInvoiceList } from '@/features/invoices/api'
import { InvoiceTable } from '@/features/invoices/InvoiceTable'
import { intParam, useDebouncedValue, useDocumentTitle, useUrlState } from '@/lib/hooks'
import type { InvoiceStatus } from '@/lib/types'

const QUEUE_FILTERS: { value: string; label: string; statuses: InvoiceStatus[] }[] = [
  { value: 'needs_review', label: 'Needs review', statuses: ['needs_review'] },
  { value: 'in_progress', label: 'Extracting', statuses: ['queued', 'processing'] },
  { value: 'failed', label: 'Failed', statuses: ['failed'] },
  {
    value: 'open',
    label: 'All open',
    statuses: ['needs_review', 'queued', 'processing', 'failed'],
  },
]

export function ReviewQueuePage() {
  useDocumentTitle('Review queue')
  const { params, update } = useUrlState()
  const filter = QUEUE_FILTERS.find((f) => f.value === params.get('filter')) ?? QUEUE_FILTERS[0]!
  const page = intParam(params.get('page'), 1)
  const pageSize = intParam(params.get('size'), 25, PAGE_SIZE_OPTIONS)
  const [search, setSearch] = useState(params.get('q') ?? '')
  const debouncedSearch = useDebouncedValue(search.trim())

  const query = useInvoiceList({
    status: filter.statuses,
    search: debouncedSearch || undefined,
    sort: 'created_at', // oldest first: first in, first reviewed
    page,
    page_size: pageSize,
  })

  const total = query.data?.total ?? 0

  return (
    <>
      <PageHeader
        title="Review queue"
        description="Bills waiting for a decision, oldest first. Open a bill to check the extracted data against the document."
        actions={
          <Link to="/upload">
            <Button variant="primary" icon="upload">
              Upload bills
            </Button>
          </Link>
        }
      />
      <Card padded={false}>
        <div className={styles.toolbar}>
          <div className={styles.search}>
            <Input
              label="Search"
              hideLabel
              placeholder="Search vendor, invoice number, GSTIN or file name"
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
              hideLabel
              value={filter.value}
              options={QUEUE_FILTERS.map(({ value, label }) => ({ value, label }))}
              onChange={(e) => update({ filter: e.target.value, page: null })}
            />
          </div>
        </div>
        <InvoiceTable
          rows={query.data?.items}
          loading={query.isFetching}
          error={query.error}
          onRetry={() => void query.refetch()}
          from="review"
          empty={
            debouncedSearch ? (
              <EmptyState
                icon="search"
                title="No bills match your search"
                description="Try a different vendor name or invoice number."
              />
            ) : filter.value === 'needs_review' ? (
              <EmptyState
                icon="check"
                title="All caught up"
                description="No bills need review right now. Uploaded bills appear here once extraction finishes."
                action={
                  <Link to="/upload">
                    <Button icon="upload">Upload bills</Button>
                  </Link>
                }
              />
            ) : (
              <EmptyState title="Nothing here" description="No bills in this state." />
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
