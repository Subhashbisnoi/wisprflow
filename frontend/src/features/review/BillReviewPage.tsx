import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Badge, Button, ErrorState, Icon, LoadingState, Spinner, useToast } from '@/components/ui'
import {
  fetchNextInReview,
  invoiceKeys,
  useAddLineItem,
  useApprove,
  useCorrectFields,
  useCorrectLineItem,
  useInvoice,
  useReject,
  useRemoveLineItem,
  useRetryExtraction,
} from '@/features/invoices/api'
import { StatusBadge } from '@/features/invoices/StatusBadge'
import { ApiError, errorMessage } from '@/lib/api'
import { formatDateTime, formatINR, pluralize } from '@/lib/format'
import { useDocumentTitle, useNow } from '@/lib/hooks'
import type { HeaderField, InvoiceDetail, LineField, LineItem } from '@/lib/types'
import { AuditTimeline } from './AuditTimeline'
import { ApproveModal, RejectModal } from './DecisionModals'
import { DocumentPreview } from './DocumentPreview'
import { FieldsPanel } from './FieldsPanel'
import { FindingsList } from './FindingsList'
import { LineItemsEditor } from './LineItemsEditor'
import styles from './Review.module.css'

type Tab = 'review' | 'activity'

export function BillReviewPage() {
  const { invoiceId = '' } = useParams()
  const [params] = useSearchParams()
  const from = params.get('from') === 'bills' ? 'bills' : 'review'
  const navigate = useNavigate()
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: invoice, error, isLoading, refetch } = useInvoice(invoiceId)
  const [tab, setTab] = useState<Tab>('review')
  const [modal, setModal] = useState<'approve' | 'reject' | null>(null)

  const correctFields = useCorrectFields(invoiceId)
  const correctLine = useCorrectLineItem(invoiceId)
  const addLine = useAddLineItem(invoiceId)
  const removeLine = useRemoveLineItem(invoiceId)
  const approve = useApprove(invoiceId)
  const reject = useReject(invoiceId)
  const retry = useRetryExtraction()

  useDocumentTitle(invoice ? `Bill ${invoice.invoice_number ?? invoice.original_filename}` : 'Bill')

  /** Shared handling for concurrent edits (D-047) and bills that were decided elsewhere. */
  const handleWriteError = (e: unknown) => {
    if (e instanceof ApiError && e.code === 'version_conflict') {
      toast.warning(
        'Someone else updated this bill',
        'You are now seeing the latest version. Re-apply your change if it is still needed.',
      )
      void refetch()
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.audit(invoiceId) })
    } else if (e instanceof ApiError && e.code === 'invalid_state') {
      toast.warning('This bill can no longer be changed', e.message)
      void refetch()
    } else if (!(e instanceof ApiError && e.code === 'validation_error')) {
      toast.error('Could not save', errorMessage(e))
    }
    throw e
  }

  const run = <T,>(promise: Promise<T>) => promise.catch(handleWriteError)

  if (isLoading) return <LoadingState label="Loading bill" />
  if (error || !invoice) {
    return (
      <div className={styles.pageError}>
        <ErrorState
          error={error ?? new Error('Bill not found')}
          onRetry={
            error instanceof ApiError && error.status === 404 ? undefined : () => void refetch()
          }
        />
        <Link to={from === 'bills' ? '/bills' : '/review'}>
          Back to {from === 'bills' ? 'bills' : 'review queue'}
        </Link>
      </div>
    )
  }

  const editable = invoice.status === 'needs_review'
  const version = invoice.version

  const saveField = (field: HeaderField, value: string | null) =>
    run(correctFields.mutateAsync({ version, changes: [{ field, value }] }))
  const saveLine = (item: LineItem, field: LineField, value: string | null) =>
    run(correctLine.mutateAsync({ itemId: item.id, version, changes: [{ field, value }] }))
  const addLineItem = (values: Partial<Record<LineField, string>>) =>
    run(addLine.mutateAsync({ version, ...values }))
  const removeLineItem = (item: LineItem) =>
    run(removeLine.mutateAsync({ itemId: item.id, version })).catch(() => undefined)

  const afterDecision = async (decided: InvoiceDetail, verb: string) => {
    setModal(null)
    toast.success(
      `Bill ${verb}`,
      `${decided.vendor?.display_name ?? decided.vendor_name ?? ''} ${decided.invoice_number ?? ''}`.trim(),
    )
    if (from === 'review') {
      const next = await fetchNextInReview(decided.id).catch(() => null)
      navigate(next ? `/bills/${next}?from=review` : '/review')
    }
  }

  const onApprove = (comment: string) =>
    approve.mutate(
      { version, comment: comment || undefined },
      {
        onSuccess: (d) => void afterDecision(d, 'approved'),
        onError: (e) => {
          setModal(null)
          if (e instanceof ApiError && e.code === 'approval_blocked') {
            toast.error('Approval blocked', e.message)
            void refetch()
          } else {
            try {
              handleWriteError(e)
            } catch {
              /* already reported */
            }
          }
        },
      },
    )

  const onReject = (reason: string) =>
    reject.mutate(
      { version, reason },
      {
        onSuccess: (d) => void afterDecision(d, 'rejected'),
        onError: (e) => {
          setModal(null)
          try {
            handleWriteError(e)
          } catch {
            /* already reported */
          }
        },
      },
    )

  const saving =
    correctFields.isPending || correctLine.isPending || addLine.isPending || removeLine.isPending

  return (
    <div className={styles.page}>
      <div className={styles.pageTop}>
        <Link to={from === 'bills' ? '/bills' : '/review'} className={styles.back}>
          <Icon name="arrowLeft" size={14} /> {from === 'bills' ? 'Bills' : 'Review queue'}
        </Link>
      </div>
      <div className={styles.split}>
        <DocumentPreview
          invoiceId={invoice.id}
          contentType={invoice.content_type}
          filename={invoice.original_filename}
          sizeBytes={invoice.file_size_bytes}
          pageCount={invoice.page_count}
        />

        <section className={styles.panel} aria-label="Extracted data">
          <header className={styles.panelHeader}>
            <div className={styles.panelTitleRow}>
              <h1 className={styles.panelTitle}>
                {invoice.vendor?.display_name ?? invoice.vendor_name ?? 'Unknown vendor'}
              </h1>
              <StatusBadge status={invoice.status} />
            </div>
            <p className={styles.panelSub}>
              <span className="mono">{invoice.invoice_number ?? 'No invoice number'}</span>
              <span aria-hidden="true"> / </span>
              <span className="tabular">{formatINR(invoice.total)}</span>
              {invoice.extraction_method && (
                <>
                  <span aria-hidden="true"> / </span>
                  <Badge tone="neutral">
                    {invoice.extraction_method === 'text_layer'
                      ? 'PDF text layer'
                      : 'Scanned (vision)'}
                  </Badge>
                </>
              )}
              {saving && (
                <span className={styles.savingNote}>
                  <Spinner size={10} /> Saving
                </span>
              )}
            </p>
            <div className={styles.tabs} role="tablist" aria-label="Bill sections">
              <button
                type="button"
                role="tab"
                aria-selected={tab === 'review'}
                className={`${styles.tab} ${tab === 'review' ? styles.tabActive : ''}`}
                onClick={() => setTab('review')}
              >
                Review
                {invoice.error_count + invoice.warning_count > 0 && (
                  <span className={styles.tabCount}>
                    {invoice.error_count + invoice.warning_count}
                  </span>
                )}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === 'activity'}
                className={`${styles.tab} ${tab === 'activity' ? styles.tabActive : ''}`}
                onClick={() => setTab('activity')}
              >
                Activity
              </button>
            </div>
          </header>

          <div className={styles.panelBody} role="tabpanel">
            <StatusBanner
              invoice={invoice}
              onRetry={() =>
                retry.mutate(invoice.id, {
                  onError: (e) => toast.error('Retry failed', errorMessage(e)),
                })
              }
              retrying={retry.isPending}
            />

            {tab === 'activity' ? (
              <AuditTimeline invoiceId={invoice.id} />
            ) : invoice.status === 'queued' ||
              invoice.status === 'processing' ||
              invoice.status === 'failed' ? null : (
              <>
                <section className={styles.section} aria-labelledby="findings-title">
                  <h2 id="findings-title" className={styles.sectionTitle}>
                    Checks
                    <span className={styles.sectionMeta}>
                      {invoice.error_count > 0 && pluralize(invoice.error_count, 'error')}
                      {invoice.error_count > 0 && invoice.warning_count > 0 && ', '}
                      {invoice.warning_count > 0 && pluralize(invoice.warning_count, 'warning')}
                    </span>
                  </h2>
                  <FindingsList findings={invoice.findings} />
                </section>
                <section className={styles.section} aria-labelledby="fields-title">
                  <h2 id="fields-title" className={styles.sectionTitle}>
                    Extracted fields
                    {editable && (
                      <span className={styles.sectionMeta}>Click a value to correct it</span>
                    )}
                  </h2>
                  <FieldsPanel invoice={invoice} editable={editable} onSave={saveField} />
                </section>
                <section className={styles.section} aria-labelledby="lines-title" id="line-items">
                  <h2 id="lines-title" className={styles.sectionTitle}>
                    Line items
                    <span className={styles.sectionMeta}>
                      {pluralize(invoice.line_items.length, 'line')}
                    </span>
                  </h2>
                  <LineItemsEditor
                    invoice={invoice}
                    editable={editable}
                    onSave={saveLine}
                    onAdd={addLineItem}
                    onRemove={removeLineItem}
                  />
                </section>
              </>
            )}
          </div>

          {editable && (
            <footer className={styles.decisionBar}>
              <p className={styles.decisionHint}>
                {invoice.error_count > 0
                  ? `Resolve ${pluralize(invoice.error_count, 'error')} or reject this bill.`
                  : 'Checked against the document? Approve to pass it for payment.'}
              </p>
              <div className={styles.decisionButtons}>
                <Button variant="danger" icon="close" onClick={() => setModal('reject')}>
                  Reject
                </Button>
                <Button
                  variant="primary"
                  icon="check"
                  onClick={() => setModal('approve')}
                  disabled={invoice.error_count > 0 || saving}
                  title={invoice.error_count > 0 ? 'Resolve errors before approving' : undefined}
                >
                  Approve
                </Button>
              </div>
            </footer>
          )}
        </section>
      </div>

      <ApproveModal
        invoice={invoice}
        open={modal === 'approve'}
        onClose={() => setModal(null)}
        onConfirm={onApprove}
        busy={approve.isPending}
      />
      <RejectModal
        open={modal === 'reject'}
        onClose={() => setModal(null)}
        onConfirm={onReject}
        busy={reject.isPending}
      />
    </div>
  )
}

function StatusBanner({
  invoice,
  onRetry,
  retrying,
}: {
  invoice: InvoiceDetail
  onRetry: () => void
  retrying: boolean
}) {
  const now = useNow()
  if (invoice.status === 'queued' || invoice.status === 'processing') {
    // Matches the API's STALE_EXTRACTION_MINUTES: a stuck job can be retried by hand.
    const stuck = now - new Date(invoice.updated_at).getTime() > 5 * 60 * 1000
    return (
      <div className={`${styles.banner} ${styles.bannerInfo}`} role="status">
        <Spinner size={14} />
        <div className={styles.bannerText}>
          <p className={styles.bannerTitle}>Reading this bill</p>
          <p>
            {stuck
              ? 'This is taking much longer than usual. Retry the extraction.'
              : (invoice.error_message ??
                'Extraction usually takes 5 to 20 seconds. This page updates automatically.')}
          </p>
        </div>
        {stuck && (
          <Button icon="refresh" onClick={onRetry} loading={retrying}>
            Retry extraction
          </Button>
        )}
      </div>
    )
  }
  if (invoice.status === 'failed') {
    return (
      <div className={`${styles.banner} ${styles.bannerError}`} role="alert">
        <Icon name="error" size={18} />
        <div className={styles.bannerText}>
          <p className={styles.bannerTitle}>Extraction failed</p>
          <p>{invoice.error_message}</p>
        </div>
        <Button icon="refresh" onClick={onRetry} loading={retrying}>
          Retry extraction
        </Button>
      </div>
    )
  }
  if (invoice.status === 'approved') {
    return (
      <div className={`${styles.banner} ${styles.bannerSuccess}`}>
        <Icon name="check" size={18} />
        <div>
          <p className={styles.bannerTitle}>
            Approved by {invoice.reviewed_by_name} on {formatDateTime(invoice.reviewed_at)}
          </p>
          {invoice.review_comment && <p>{invoice.review_comment}</p>}
        </div>
      </div>
    )
  }
  if (invoice.status === 'rejected') {
    return (
      <div className={`${styles.banner} ${styles.bannerError}`}>
        <Icon name="close" size={18} />
        <div>
          <p className={styles.bannerTitle}>
            Rejected by {invoice.reviewed_by_name} on {formatDateTime(invoice.reviewed_at)}
          </p>
          {invoice.rejection_reason && <p>Reason: {invoice.rejection_reason}</p>}
        </div>
      </div>
    )
  }
  if (
    invoice.extraction_method === 'vision' &&
    invoice.page_count &&
    invoice.pages_processed &&
    invoice.page_count > invoice.pages_processed
  ) {
    return (
      <div className={`${styles.banner} ${styles.bannerInfo}`}>
        <Icon name="info" size={18} />
        <p>
          Pages 1 to {invoice.pages_processed} of {invoice.page_count} were read. Check the
          remaining pages for extra line items.
        </p>
      </div>
    )
  }
  return null
}
