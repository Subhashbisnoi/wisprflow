// Thin fetch wrapper: auth header, consistent error envelope (D-060), session expiry hook.

const TOKEN_KEY = 'ledgerline.token'
export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    requestId?: string | null,
  ) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId ?? null
  }

  /** Field-level messages from a 422 validation_error, keyed by field name. */
  fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {}
    const out: Record<string, string> = {}
    for (const d of this.details as { field?: string; message?: string }[]) {
      if (d.field && d.message) out[d.field] = d.message.replace(/^Value error, /, '')
    }
    return out
  }
}

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

type SessionExpiredHandler = (reason: 'expired' | 'invalid') => void
let onSessionExpired: SessionExpiredHandler | null = null
export function setSessionExpiredHandler(handler: SessionExpiredHandler | null) {
  onSessionExpired = handler
}

type QueryValue = string | number | boolean | null | undefined | (string | number)[]

export function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)))
    else params.append(key, String(value))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, QueryValue>
  signal?: AbortSignal
}

async function toApiError(response: Response): Promise<ApiError> {
  let payload: {
    error?: { code?: string; message?: string; details?: unknown; request_id?: string }
  } = {}
  try {
    payload = await response.json()
  } catch {
    /* non-JSON error (proxy down, etc.) */
  }
  const err = payload.error
  return new ApiError(
    response.status,
    err?.code ?? (response.status >= 500 ? 'internal_error' : 'request_failed'),
    err?.message ??
      (response.status >= 500
        ? 'The server is not responding. Please try again.'
        : 'Request failed.'),
    err?.details,
    err?.request_id ?? response.headers.get('X-Request-ID'),
  )
}

function handleAuthError(error: ApiError) {
  if (error.status === 401 && (error.code === 'token_expired' || error.code === 'invalid_token')) {
    tokenStore.clear()
    onSessionExpired?.(error.code === 'token_expired' ? 'expired' : 'invalid')
  }
}

export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (options.body instanceof FormData) body = options.body
  else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}${buildQuery(options.query)}`, {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: options.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection.')
  }
  if (!response.ok) {
    const error = await toApiError(response)
    handleAuthError(error)
    throw error
  }
  return response
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Multipart upload with progress events (fetch has no upload progress). */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`)
    const token = tokenStore.get()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onerror = () =>
      reject(new ApiError(0, 'network_error', 'Upload failed. Check your connection.'))
    xhr.onload = () => {
      let payload: unknown = null
      try {
        payload = JSON.parse(xhr.responseText)
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as T)
        return
      }
      const err = (
        payload as {
          error?: { code: string; message: string; details?: unknown; request_id?: string }
        }
      )?.error
      const error = new ApiError(
        xhr.status,
        err?.code ?? 'upload_failed',
        err?.message ?? 'Upload failed.',
        err?.details,
        err?.request_id,
      )
      handleAuthError(error)
      reject(error)
    }
    xhr.send(form)
  })
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}
