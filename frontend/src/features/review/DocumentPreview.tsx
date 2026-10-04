import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { Button, ErrorState, LoadingState } from '@/components/ui'
import { request } from '@/lib/api'
import { formatBytes } from '@/lib/format'
import styles from './Review.module.css'

/**
 * The file endpoint is tenant-protected, so the document is fetched with the bearer token
 * and shown through an object URL (D-085).
 */
export function DocumentPreview({
  invoiceId,
  contentType,
  filename,
  sizeBytes,
  pageCount,
}: {
  invoiceId: string
  contentType: string
  filename: string
  sizeBytes: number
  pageCount: number | null
}) {
  const file = useQuery({
    queryKey: ['invoices', 'file', invoiceId],
    queryFn: async () => (await request(`/invoices/${invoiceId}/file`)).blob(),
    staleTime: Infinity,
    gcTime: 60_000,
  })
  const url = useMemo(() => (file.data ? URL.createObjectURL(file.data) : null), [file.data])
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [url])

  const isPdf = contentType === 'application/pdf'
  return (
    <section className={styles.preview} aria-label="Original document">
      <header className={styles.previewBar}>
        <div className={styles.previewMeta}>
          <p className={styles.previewName} title={filename}>
            {filename}
          </p>
          <p className={styles.previewSub}>
            {isPdf ? 'PDF' : contentType.replace('image/', '').toUpperCase()} /{' '}
            {formatBytes(sizeBytes)}
            {pageCount ? ` / ${pageCount} ${pageCount === 1 ? 'page' : 'pages'}` : ''}
          </p>
        </div>
        {url && (
          <Button
            size="sm"
            variant="ghost"
            icon="external"
            onClick={() => window.open(url, '_blank', 'noopener')}
          >
            Open
          </Button>
        )}
      </header>
      <div className={styles.previewBody}>
        {file.isLoading && <LoadingState label="Loading document" />}
        {file.error && <ErrorState error={file.error} onRetry={() => void file.refetch()} />}
        {url && isPdf && (
          <iframe
            className={styles.previewFrame}
            src={`${url}#view=FitH&navpanes=0`}
            title={`Document: ${filename}`}
          />
        )}
        {url && !isPdf && (
          <div className={styles.previewImageWrap}>
            <img className={styles.previewImage} src={url} alt={`Scanned invoice ${filename}`} />
          </div>
        )}
      </div>
    </section>
  )
}
