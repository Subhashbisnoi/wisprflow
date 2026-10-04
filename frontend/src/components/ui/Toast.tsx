import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Icon, type IconName } from './Icon'
import styles from './Toast.module.css'

type ToastTone = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
  id: number
  tone: ToastTone
  title: string
  description?: string
}

interface ToastApi {
  show: (tone: ToastTone, title: string, description?: string) => void
  success: (title: string, description?: string) => void
  error: (title: string, description?: string) => void
  warning: (title: string, description?: string) => void
  info: (title: string, description?: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const ICONS: Record<ToastTone, IconName> = {
  success: 'check',
  error: 'error',
  warning: 'alert',
  info: 'info',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((items) => items.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (tone: ToastTone, title: string, description?: string) => {
      const id = nextId.current++
      setToasts((items) => [...items.slice(-3), { id, tone, title, description }])
      window.setTimeout(() => dismiss(id), tone === 'error' ? 8000 : 5000)
    },
    [dismiss],
  )

  const api = useMemo<ToastApi>(
    () => ({
      show,
      success: (t, d) => show('success', t, d),
      error: (t, d) => show('error', t, d),
      warning: (t, d) => show('warning', t, d),
      info: (t, d) => show('info', t, d),
    }),
    [show],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className={styles.region} role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`${styles.toast} ${styles[t.tone]}`}
            role={t.tone === 'error' ? 'alert' : 'status'}
          >
            <span className={styles.icon}>
              <Icon name={ICONS[t.tone]} size={18} />
            </span>
            <div className={styles.text}>
              <p className={styles.title}>{t.title}</p>
              {t.description && <p className={styles.description}>{t.description}</p>}
            </div>
            <button
              type="button"
              className={styles.close}
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
