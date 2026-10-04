import { useState, type FormEvent } from 'react'
import { Button, Icon } from '@/components/ui'
import { errorMessage } from '@/lib/api'
import { formatINR } from '@/lib/format'
import type { InvoiceDetail, LineField, LineItem } from '@/lib/types'
import { EditableValue } from './EditableValue'
import { LINE_FIELDS, severityByField } from './fieldMeta'
import styles from './Review.module.css'

const COLUMNS: LineField[] = ['description', 'hsn_sac', 'quantity', 'rate', 'amount']

interface Props {
  invoice: InvoiceDetail
  editable: boolean
  onSave: (item: LineItem, field: LineField, value: string | null) => Promise<unknown>
  onAdd: (values: Partial<Record<LineField, string>>) => Promise<unknown>
  onRemove: (item: LineItem) => Promise<unknown>
}

export function LineItemsEditor({ invoice, editable, onSave, onAdd, onRemove }: Props) {
  const severities = severityByField(invoice.findings)
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState<Partial<Record<LineField, string>>>({})
  const [addError, setAddError] = useState<string | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const lineSum = invoice.line_items.reduce(
    (sum, li) => sum + (li.amount ? Number(li.amount) : 0),
    0,
  )
  const subtotal = invoice.subtotal ? Number(invoice.subtotal) : null
  const mismatch =
    subtotal !== null && invoice.line_items.length > 0 && Math.abs(lineSum - subtotal) > 1

  const submitAdd = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setAddError(null)
    try {
      await onAdd(draft)
      setDraft({})
      setAdding(false)
    } catch (e) {
      setAddError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className={styles.lineTableWrap}>
        <table className={styles.lineTable}>
          <thead>
            <tr>
              <th scope="col" className={styles.lineIndex}>
                #
              </th>
              {COLUMNS.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className={LINE_FIELDS[c].kind === 'text' ? undefined : styles.numHeader}
                >
                  {LINE_FIELDS[c].label}
                </th>
              ))}
              {editable && (
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {invoice.line_items.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length + 2} className={styles.lineEmpty}>
                  No line items were extracted.
                </td>
              </tr>
            )}
            {invoice.line_items.map((item) => (
              <tr key={item.id}>
                <td className={`${styles.lineIndex} tabular`}>{item.position}</td>
                {COLUMNS.map((c) => (
                  <td key={c} className={c === 'description' ? styles.lineDescription : undefined}>
                    <EditableValue
                      compact
                      kind={LINE_FIELDS[c].kind}
                      value={item[c]}
                      label={`Line ${item.position} ${LINE_FIELDS[c].label}`}
                      editable={editable}
                      severity={severities.get(`line_items.${item.position}.${c}`)}
                      placeholder="-"
                      onSave={(v) => onSave(item, c, v)}
                    />
                  </td>
                ))}
                {editable && (
                  <td className={styles.lineActions}>
                    {confirmRemove === item.id ? (
                      <span className={styles.confirmRemove}>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => {
                            setConfirmRemove(null)
                            void onRemove(item)
                          }}
                        >
                          Remove
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(null)}>
                          Keep
                        </Button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className={styles.iconButton}
                        onClick={() => setConfirmRemove(item.id)}
                        aria-label={`Remove line ${item.position}`}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
          {invoice.line_items.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan={COLUMNS.length} className={styles.lineSumLabel}>
                  Sum of line amounts
                  {mismatch && (
                    <span className={styles.lineSumWarn}> (subtotal is {formatINR(subtotal)})</span>
                  )}
                </td>
                <td className={`${styles.lineSum} tabular ${mismatch ? styles.lineSumBad : ''}`}>
                  {formatINR(lineSum)}
                </td>
                {editable && <td />}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {editable &&
        (adding ? (
          <form className={styles.addLine} onSubmit={submitAdd}>
            {COLUMNS.map((c) => (
              <input
                key={c}
                className={`${styles.addInput} ${c === 'description' ? styles.addInputWide : ''}`}
                placeholder={LINE_FIELDS[c].label}
                aria-label={`New line ${LINE_FIELDS[c].label}`}
                inputMode={LINE_FIELDS[c].kind === 'text' ? undefined : 'decimal'}
                value={draft[c] ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, [c]: e.target.value }))}
              />
            ))}
            <Button size="sm" type="submit" variant="primary" loading={busy}>
              Add
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
            {addError && <p className={styles.editorError}>{addError}</p>}
          </form>
        ) : (
          <div className={styles.addLineTrigger}>
            <Button size="sm" variant="ghost" icon="plus" onClick={() => setAdding(true)}>
              Add line item
            </Button>
          </div>
        ))}
    </div>
  )
}
