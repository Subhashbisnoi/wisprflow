import { useCallback, useMemo, useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Card, EmptyState, Icon, Spinner, useToast } from '@/components/ui'
import { useInvoiceList, useRetryExtraction } from '@/features/invoices/api'
import { IssueCounts, StatusBadge } from '@/features/invoices/StatusBadge'
import { vendorLabel } from '@/features/invoices/status'
import { ApiError, errorMessage, uploadWithProgress } from '@/lib/api'
import { formatBytes, formatINR, pluralize } from '@/lib/format'
import { useDocumentTitle } from '@/lib/hooks'
import type { InvoiceSummary, UploadResponse } from '@/lib/types'
import styles from './Upload.module.css'

const MAX_FILE_MB = 15
const MAX_FILES = 20
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp'
const ACCEPTED_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp']
const PARALLEL_UPLOADS = 3

type RowState = 'rejected' | 'waiting' | 'uploading' | 'accepted'

interface UploadRow {
  key: string
  file: File
  state: RowState
  progress: number
  error?: string
  invoiceId?: string
}

function precheck(file: File): string | null {
  const byExtension = /\.(pdf|png|jpe?g|webp)$/i.test(file.name)
  if (!ACCEPTED_TYPES.includes(file.type) && !byExtension)
    return 'Only PDF, PNG, JPG and WEBP files are supported.'
  if (file.size === 0) return 'File is empty.'
  if (file.size > MAX_FILE_MB * 1024 * 1024)
    return `File is ${formatBytes(file.size)}; the limit is ${MAX_FILE_MB} MB. Compress or split the PDF.`
  return null
}

let rowCounter = 0

export function UploadPage() {
  useDocumentTitle('Upload')
  const toast = useToast()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [rows, setRows] = useState<UploadRow[]>([])
  const [dragging, setDragging] = useState(false)
  const retry = useRetryExtraction()

  const patch = useCallback((key: string, update: Partial<UploadRow>) => {
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...update } : r)))
  }, [])

  const uploadOne = useCallback(
    async (row: UploadRow) => {
      patch(row.key, { state: 'uploading', progress: 0 })
      const form = new FormData()
      form.append('files', row.file, row.file.name)
      try {
        const res = await uploadWithProgress<UploadResponse>('/invoices', form, (p) =>
          patch(row.key, { progress: p }),
        )
        const result = res.results[0]
        if (result?.status === 'accepted' && result.invoice) {
          patch(row.key, { state: 'accepted', progress: 1, invoiceId: result.invoice.id })
        } else {
          patch(row.key, { state: 'rejected', error: result?.error?.message ?? 'Upload rejected.' })
        }
      } catch (e) {
        patch(row.key, { state: 'rejected', error: errorMessage(e) })
        if (e instanceof ApiError && e.status === 401) throw e
      }
    },
    [patch],
  )

  const addFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList)
      if (!files.length) return
      if (files.length > MAX_FILES) toast.warning(`Only the first ${MAX_FILES} files were added`)
      const fresh: UploadRow[] = files.slice(0, MAX_FILES).map((file) => {
        const error = precheck(file)
        return {
          key: `row-${++rowCounter}`,
          file,
          state: error ? 'rejected' : 'waiting',
          progress: 0,
          error: error ?? undefined,
        }
      })
      setRows((current) => [...fresh, ...current])
      const queue = fresh.filter((r) => r.state === 'waiting')
      const workers = Array.from({ length: Math.min(PARALLEL_UPLOADS, queue.length) }, async () => {
        for (let row = queue.shift(); row; row = queue.shift()) await uploadOne(row)
      })
      await Promise.allSettled(workers)
    },
    [toast, uploadOne],
  )

  const acceptedIds = useMemo(
    () => rows.filter((r) => r.invoiceId).map((r) => r.invoiceId as string),
    [rows],
  )
  const { data: statusPage } = useInvoiceList(
    { ids: acceptedIds, page_size: 100 },
    { enabled: acceptedIds.length > 0 },
  )
  const byId = useMemo(() => {
    const map = new Map<string, InvoiceSummary>()
    if (acceptedIds.length) statusPage?.items.forEach((i) => map.set(i.id, i))
    return map
  }, [statusPage, acceptedIds])

  const ready = acceptedIds.filter((id) => byId.get(id)?.status === 'needs_review').length
  const failed = acceptedIds.filter((id) => byId.get(id)?.status === 'failed').length
  const inFlight = rows.filter(
    (r) =>
      r.state === 'uploading' ||
      r.state === 'waiting' ||
      (r.invoiceId && ['queued', 'processing'].includes(byId.get(r.invoiceId)?.status ?? 'queued')),
  ).length

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    void addFiles(event.dataTransfer.files)
  }

  return (
    <>
      <PageHeader
        title="Upload bills"
        description="Drop vendor invoices as PDF or images. Each file is read, checked and placed in the review queue."
        actions={
          ready > 0 ? (
            <Button variant="primary" icon="inbox" onClick={() => navigate('/review')}>
              Open review queue
            </Button>
          ) : undefined
        }
      />

      <div
        className={`${styles.dropzone} ${dragging ? styles.dragging : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <span className={styles.dropIcon}>
          <Icon name="upload" size={24} />
        </span>
        <p className={styles.dropTitle}>Drag and drop invoices here</p>
        <p className={styles.dropHint}>
          PDF, PNG, JPG or WEBP. Up to {MAX_FILES} files at a time, {MAX_FILE_MB} MB each.
        </p>
        <Button variant="secondary" onClick={() => inputRef.current?.click()}>
          Browse files
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="visually-hidden"
          aria-label="Choose invoice files"
          onChange={(e) => {
            if (e.target.files) void addFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      <Card
        className={styles.listCard}
        padded={false}
        title="This session"
        subtitle={
          rows.length
            ? [
                pluralize(rows.length, 'file'),
                ready && `${ready} ready for review`,
                failed && `${failed} failed`,
                inFlight && `${inFlight} in progress`,
              ]
                .filter(Boolean)
                .join(' / ')
            : undefined
        }
        actions={
          rows.length ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setRows((r) => r.filter((x) => x.state === 'uploading' || x.state === 'waiting'))
              }
            >
              Clear list
            </Button>
          ) : undefined
        }
      >
        {rows.length === 0 ? (
          <EmptyState
            icon="file"
            title="No files uploaded yet"
            description="Files you upload here appear with their live status. Sample invoices are in the samples folder of the repository."
          />
        ) : (
          <ul className={styles.list} aria-live="polite">
            {rows.map((row) => {
              const invoice = row.invoiceId ? byId.get(row.invoiceId) : undefined
              return (
                <li key={row.key} className={styles.row}>
                  <span className={styles.fileIcon}>
                    <Icon name={row.file.type.startsWith('image/') ? 'image' : 'file'} size={18} />
                  </span>
                  <div className={styles.fileMeta}>
                    <p className={styles.fileName}>{row.file.name}</p>
                    <p className={styles.fileSub}>
                      {formatBytes(row.file.size)}
                      {invoice?.status === 'needs_review' && (
                        <>
                          {' / '}
                          {vendorLabel(invoice)}
                          {' / '}
                          <span className="tabular">{formatINR(invoice.total)}</span>
                        </>
                      )}
                    </p>
                    {row.state === 'uploading' && (
                      <div
                        className={styles.progress}
                        role="progressbar"
                        aria-label={`Uploading ${row.file.name}`}
                        aria-valuenow={Math.round(row.progress * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <span style={{ width: `${Math.max(4, row.progress * 100)}%` }} />
                      </div>
                    )}
                    {(row.error || invoice?.status === 'failed') && (
                      <p className={styles.rowError}>{row.error ?? invoice?.error_message}</p>
                    )}
                  </div>
                  <div className={styles.rowStatus}>
                    {row.state === 'rejected' && <Badge tone="error">Rejected</Badge>}
                    {row.state === 'waiting' && <Badge tone="neutral">Waiting</Badge>}
                    {row.state === 'uploading' && (
                      <Badge tone="neutral">
                        <Spinner size={10} /> Uploading {Math.round(row.progress * 100)}%
                      </Badge>
                    )}
                    {row.state === 'accepted' && !invoice && <Badge tone="neutral">Queued</Badge>}
                    {invoice && invoice.status === 'processing' && (
                      <Badge tone="neutral">
                        <Spinner size={10} /> Extracting
                      </Badge>
                    )}
                    {invoice && invoice.status !== 'processing' && (
                      <StatusBadge status={invoice.status} />
                    )}
                    {invoice?.status === 'needs_review' && (
                      <IssueCounts errors={invoice.error_count} warnings={invoice.warning_count} />
                    )}
                  </div>
                  <div className={styles.rowActions}>
                    {invoice?.status === 'failed' && (
                      <Button
                        size="sm"
                        icon="refresh"
                        loading={retry.isPending && retry.variables === invoice.id}
                        onClick={() =>
                          retry.mutate(invoice.id, {
                            onError: (e) => toast.error('Retry failed', errorMessage(e)),
                          })
                        }
                      >
                        Retry
                      </Button>
                    )}
                    {invoice &&
                      ['needs_review', 'approved', 'rejected'].includes(invoice.status) && (
                        <Link className={styles.openLink} to={`/bills/${invoice.id}?from=review`}>
                          Open
                        </Link>
                      )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </>
  )
}
