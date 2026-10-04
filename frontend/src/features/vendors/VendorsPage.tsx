import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Icon,
  Input,
  LoadingState,
  Pager,
  PAGE_SIZE_OPTIONS,
  Table,
  useToast,
  type Column,
} from '@/components/ui'
import styles from '@/features/bills/Filters.module.css'
import { useInvoiceList } from '@/features/invoices/api'
import { StatusBadge } from '@/features/invoices/StatusBadge'
import { errorMessage } from '@/lib/api'
import { formatDate, formatINR } from '@/lib/format'
import { intParam, useDebouncedValue, useDocumentTitle, useUrlState } from '@/lib/hooks'
import type { Vendor } from '@/lib/types'
import { useUpdateVendor, useVendor, useVendors } from './api'
import vstyles from './Vendors.module.css'

const columns: Column<Vendor>[] = [
  {
    key: 'name',
    header: 'Vendor',
    render: (v) => (
      <div className={vstyles.nameCell}>
        <span className={vstyles.displayName}>{v.display_name}</span>
        {v.legal_name !== v.display_name && (
          <span className={vstyles.legalName}>{v.legal_name}</span>
        )}
      </div>
    ),
  },
  {
    key: 'legal',
    header: 'Legal name',
    render: (v) => <span className="secondary">{v.legal_name}</span>,
  },
  {
    key: 'gstin',
    header: 'GSTIN',
    render: (v) => <span className="mono">{v.gstin}</span>,
    width: 170,
  },
  { key: 'state', header: 'State', render: (v) => v.state_name, width: 150 },
  { key: 'bills', header: 'Bills', numeric: true, render: (v) => v.bill_count, width: 70 },
  {
    key: 'pending',
    header: 'Pending',
    numeric: true,
    render: (v) => formatINR(v.pending_amount),
    width: 140,
  },
  {
    key: 'spend',
    header: 'Approved spend',
    numeric: true,
    render: (v) => formatINR(v.approved_spend),
    width: 150,
  },
]

export function VendorsPage() {
  useDocumentTitle('Vendors')
  const { params, update } = useUrlState()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const debounced = useDebouncedValue(search.trim())
  const page = intParam(params.get('page'), 1)
  const pageSize = intParam(params.get('size'), 25, PAGE_SIZE_OPTIONS)
  const selected = params.get('vendor')
  const query = useVendors({ search: debounced || undefined, page, page_size: pageSize })

  return (
    <>
      <PageHeader
        title="Vendors"
        description="Vendors are created automatically from the first invoice with a new GSTIN. Rename them to the brand name your team uses."
      />
      <Card padded={false}>
        <div className={styles.toolbar}>
          <div className={styles.search}>
            <Input
              label="Search vendors"
              hideLabel
              placeholder="Search by name or GSTIN"
              value={search}
              leading={<Icon name="search" />}
              onChange={(e) => {
                setSearch(e.target.value)
                update({ q: e.target.value, page: null })
              }}
            />
          </div>
        </div>
        <Table
          columns={columns}
          rows={query.data?.items}
          getRowId={(v) => v.id}
          loading={query.isFetching}
          error={query.error}
          onRetry={() => void query.refetch()}
          onRowClick={(v) => update({ vendor: v.id })}
          rowLabel={(v) => `Open vendor ${v.display_name}`}
          caption="Vendors"
          empty={
            debounced ? (
              <EmptyState icon="search" title="No vendors match your search" />
            ) : (
              <EmptyState
                icon="vendors"
                title="No vendors yet"
                description="Vendors appear here automatically when you upload their first invoice."
                action={
                  <Link to="/upload">
                    <Button icon="upload">Upload bills</Button>
                  </Link>
                }
              />
            )
          }
        />
        {(query.data?.total ?? 0) > 0 && (
          <Pager
            page={query.data?.page ?? page}
            pageSize={pageSize}
            total={query.data?.total ?? 0}
            onPageChange={(p) => update({ page: p })}
            onPageSizeChange={(s) => update({ size: s, page: null })}
          />
        )}
      </Card>
      <VendorDrawer vendorId={selected} onClose={() => update({ vendor: null })} />
    </>
  )
}

function VendorDrawer({ vendorId, onClose }: { vendorId: string | null; onClose: () => void }) {
  const vendor = useVendor(vendorId)
  const bills = useInvoiceList(
    { vendor_id: vendorId ?? undefined, page_size: 5, sort: '-invoice_date' },
    { enabled: Boolean(vendorId) },
  )
  const v = vendor.data
  return (
    <Drawer
      open={Boolean(vendorId)}
      onClose={onClose}
      title={v?.display_name ?? 'Vendor'}
      description={v ? `GSTIN ${v.gstin} / ${v.state_name}` : undefined}
    >
      {vendor.isLoading && <LoadingState label="Loading vendor" />}
      {vendor.error && <ErrorState error={vendor.error} onRetry={() => void vendor.refetch()} />}
      {v && (
        <div className={vstyles.drawer}>
          <dl className={vstyles.stats}>
            <div>
              <dt>Bills</dt>
              <dd className="tabular">{v.bill_count}</dd>
            </div>
            <div>
              <dt>Pending review</dt>
              <dd className="tabular">{formatINR(v.pending_amount)}</dd>
            </div>
            <div>
              <dt>Approved spend</dt>
              <dd className="tabular">{formatINR(v.approved_spend)}</dd>
            </div>
          </dl>

          <VendorNameForm key={`${v.id}:${v.display_name}`} vendor={v} />

          <div className={vstyles.recent}>
            <div className={vstyles.recentHeader}>
              <h3>Recent bills</h3>
              <Link to={`/bills?vendor=${v.id}`}>View all bills</Link>
            </div>
            {bills.isLoading && <LoadingState label="Loading bills" />}
            {bills.data && bills.data.items.length === 0 && (
              <p className="muted">No bills from this vendor yet.</p>
            )}
            <ul className={vstyles.recentList}>
              {bills.data?.items.map((b) => (
                <li key={b.id}>
                  <Link to={`/bills/${b.id}?from=bills`} className={vstyles.recentItem}>
                    <span>
                      <span className="mono">{b.invoice_number ?? b.original_filename}</span>
                      <span className={vstyles.recentDate}>{formatDate(b.invoice_date)}</span>
                    </span>
                    <span className={vstyles.recentRight}>
                      <span className="tabular">{formatINR(b.total)}</span>
                      <StatusBadge status={b.status} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            <p className={vstyles.since}>
              <Badge tone="neutral">Added {formatDate(v.created_at)}</Badge>
            </p>
          </div>
        </div>
      )}
    </Drawer>
  )
}

/** Keyed by vendor + saved name, so the field resets from props without an effect. */
function VendorNameForm({ vendor }: { vendor: Vendor }) {
  const toast = useToast()
  const updateVendor = useUpdateVendor()
  const [name, setName] = useState(vendor.display_name)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Display name cannot be blank.')
      return
    }
    updateVendor.mutate(
      { id: vendor.id, display_name: name.trim() },
      {
        onSuccess: () => toast.success('Vendor updated'),
        onError: (e) => setError(errorMessage(e)),
      },
    )
  }

  return (
    <form onSubmit={onSubmit} className={vstyles.form}>
      <Input
        label="Display (brand) name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error}
        hint="Shown across Ledgerline. The legal name stays as printed on invoices."
        maxLength={300}
      />
      <Input label="Legal name" value={vendor.legal_name} readOnly disabled />
      <div>
        <Button
          type="submit"
          variant="primary"
          loading={updateVendor.isPending}
          disabled={name.trim() === vendor.display_name}
        >
          Save changes
        </Button>
      </div>
    </form>
  )
}
