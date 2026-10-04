import { useState } from 'react'
import { Button, Modal } from '@/components/ui'
import { formatINR } from '@/lib/format'
import type { InvoiceDetail } from '@/lib/types'
import styles from './Review.module.css'

const REJECT_REASONS = [
  'Duplicate bill',
  'Goods or services not received',
  'Amount does not match the purchase order',
  'Not addressed to our company',
  'Invalid or missing GSTIN',
]

export function ApproveModal({
  invoice,
  open,
  onClose,
  onConfirm,
  busy,
}: {
  invoice: InvoiceDetail
  open: boolean
  onClose: () => void
  onConfirm: (comment: string) => void
  busy: boolean
}) {
  const [comment, setComment] = useState('')
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Approve bill"
      description={`${invoice.vendor?.display_name ?? invoice.vendor_name ?? 'Vendor'} / ${invoice.invoice_number ?? ''} / ${formatINR(invoice.total)}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" icon="check" loading={busy} onClick={() => onConfirm(comment)}>
            Approve
          </Button>
        </>
      }
    >
      {invoice.warning_count > 0 && (
        <p className={styles.modalNote}>
          This bill has {invoice.warning_count}{' '}
          {invoice.warning_count === 1 ? 'warning' : 'warnings'}. Approving confirms you have
          checked them.
        </p>
      )}
      <label className={styles.modalLabel} htmlFor="approve-comment">
        Comment (optional)
      </label>
      <textarea
        id="approve-comment"
        className={styles.textarea}
        rows={3}
        maxLength={1000}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="For example: matched with PO 4471"
      />
    </Modal>
  )
}

export function RejectModal({
  open,
  onClose,
  onConfirm,
  busy,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (reason: string) => void
  busy: boolean
}) {
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const invalid = reason.trim().length < 3
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reject bill"
      description="The reason is recorded in the audit trail and shown to your team."
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="danger"
            icon="close"
            loading={busy}
            onClick={() => {
              setTouched(true)
              if (!invalid) onConfirm(reason.trim())
            }}
          >
            Reject bill
          </Button>
        </>
      }
    >
      <div className={styles.reasonChips} role="group" aria-label="Common reasons">
        {REJECT_REASONS.map((r) => (
          <button
            key={r}
            type="button"
            className={`${styles.reasonChip} ${reason === r ? styles.reasonChipActive : ''}`}
            onClick={() => setReason(r)}
            aria-pressed={reason === r}
          >
            {r}
          </button>
        ))}
      </div>
      <label className={styles.modalLabel} htmlFor="reject-reason">
        Reason
      </label>
      <textarea
        id="reject-reason"
        className={`${styles.textarea} ${touched && invalid ? styles.textareaInvalid : ''}`}
        rows={3}
        maxLength={1000}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        onBlur={() => setTouched(true)}
        aria-invalid={touched && invalid ? true : undefined}
        aria-describedby={touched && invalid ? 'reject-reason-error' : undefined}
      />
      {touched && invalid && (
        <p id="reject-reason-error" className={styles.editorError} role="alert">
          Give a reason of at least 3 characters.
        </p>
      )}
    </Modal>
  )
}
