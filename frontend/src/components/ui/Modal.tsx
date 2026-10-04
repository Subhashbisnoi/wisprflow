import { useEffect, useRef, type ReactNode } from 'react'
import { Icon } from './Icon'
import styles from './Overlay.module.css'

interface OverlayProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  footer?: ReactNode
  children?: ReactNode
}

/**
 * Native <dialog> + showModal(): built-in focus trapping, Escape handling, inert background
 * and focus restoration, so the overlay is accessible without extra libraries.
 */
function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const handleCancel = (event: Event) => {
      event.preventDefault()
      onClose()
    }
    dialog.addEventListener('cancel', handleCancel)
    return () => dialog.removeEventListener('cancel', handleCancel)
  }, [onClose])
  const onBackdropClick = (event: React.MouseEvent<HTMLDialogElement>) => {
    if (event.target === ref.current) onClose()
  }
  return { ref, onBackdropClick }
}

export function Modal({ open, onClose, title, description, footer, children }: OverlayProps) {
  const { ref, onBackdropClick } = useDialog(open, onClose)
  return (
    <dialog
      ref={ref}
      className={styles.modal}
      onClick={onBackdropClick}
      aria-labelledby="modal-title"
    >
      {open && (
        <div className={styles.modalInner}>
          <header className={styles.header}>
            <div>
              <h2 id="modal-title" className={styles.title}>
                {title}
              </h2>
              {description && <p className={styles.description}>{description}</p>}
            </div>
            <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
              <Icon name="close" />
            </button>
          </header>
          {children && <div className={styles.body}>{children}</div>}
          {footer && <footer className={styles.footer}>{footer}</footer>}
        </div>
      )}
    </dialog>
  )
}

export function Drawer({ open, onClose, title, description, footer, children }: OverlayProps) {
  const { ref, onBackdropClick } = useDialog(open, onClose)
  return (
    <dialog
      ref={ref}
      className={styles.drawer}
      onClick={onBackdropClick}
      aria-labelledby="drawer-title"
    >
      {open && (
        <div className={styles.drawerInner}>
          <header className={styles.header}>
            <div>
              <h2 id="drawer-title" className={styles.title}>
                {title}
              </h2>
              {description && <p className={styles.description}>{description}</p>}
            </div>
            <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
              <Icon name="close" />
            </button>
          </header>
          <div className={`${styles.body} ${styles.drawerBody}`}>{children}</div>
          {footer && <footer className={styles.footer}>{footer}</footer>}
        </div>
      )}
    </dialog>
  )
}
