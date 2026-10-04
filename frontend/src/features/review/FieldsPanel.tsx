import type { HeaderField, InvoiceDetail } from '@/lib/types'
import { EditableValue } from './EditableValue'
import { confidenceLevel, FIELD_GROUPS, HEADER_FIELDS, severityByField } from './fieldMeta'
import styles from './Review.module.css'

function ConfidenceTag({ value }: { value: number | undefined }) {
  const level = confidenceLevel(value)
  if (!level || value === undefined) return null
  const pct = Math.round(value * 100)
  const text = level === 'high' ? 'High' : level === 'medium' ? 'Medium' : 'Low'
  return (
    <span
      className={`${styles.confidence} ${styles[`confidence_${level}`]}`}
      title={`Extraction confidence ${pct}%`}
    >
      <span className={styles.confidenceDot} aria-hidden="true" />
      {text}
      <span className="visually-hidden"> confidence, {pct}%</span>
    </span>
  )
}

export function FieldsPanel({
  invoice,
  editable,
  onSave,
}: {
  invoice: InvoiceDetail
  editable: boolean
  onSave: (field: HeaderField, value: string | null) => Promise<unknown>
}) {
  const severities = severityByField(invoice.findings)
  return (
    <div className={styles.fieldGroups}>
      {FIELD_GROUPS.map((group) => (
        <fieldset key={group.title} className={styles.fieldGroup}>
          <legend className={styles.groupTitle}>{group.title}</legend>
          <dl className={styles.fieldList}>
            {group.fields.map((field) => {
              const meta = HEADER_FIELDS[field]
              const value = invoice[field]
              const severity = severities.get(field)
              return (
                <div key={field} className={styles.fieldRow} id={`field-${field}`}>
                  <dt className={styles.fieldLabel}>
                    {meta.label}
                    {value !== null && <ConfidenceTag value={invoice.field_confidence[field]} />}
                  </dt>
                  <dd className={styles.fieldValue}>
                    <EditableValue
                      kind={meta.kind}
                      value={value}
                      label={meta.label}
                      editable={editable}
                      severity={severity}
                      onSave={(v) => onSave(field, v)}
                      placeholder={
                        field === 'cgst' || field === 'sgst' || field === 'igst'
                          ? 'Not charged'
                          : 'Not found'
                      }
                    />
                  </dd>
                </div>
              )
            })}
          </dl>
        </fieldset>
      ))}
    </div>
  )
}
