// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = any

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function request(method: string, url: string, body?: unknown, isForm = false): Promise<Json> {
  const res = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  })
  if (res.status === 401 && !url.endsWith('/auth/login')) {
    window.dispatchEvent(new Event('auth:expired'))
  }
  const type = res.headers.get('content-type') || ''
  const data = type.includes('json') ? await res.json() : await res.text()
  if (!res.ok) {
    const msg = typeof data === 'object' && data?.error ? data.error
      : res.status === 403 ? 'You do not have access to this.' : `Request failed (${res.status})`
    throw new ApiError(res.status, msg)
  }
  return data
}

export const api = {
  get: (url: string) => request('GET', url),
  post: (url: string, body?: unknown) => request('POST', url, body ?? {}),
  put: (url: string, body?: unknown) => request('PUT', url, body ?? {}),
  del: (url: string) => request('DELETE', url),
  upload: (url: string, form: FormData) => request('POST', url, form, true),
}

export function qs(params: Record<string, unknown>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const fmtDate = (v?: string | null) => (v ? new Date(v).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—')
export const fmtTime = (v?: string | null) =>
  v ? new Date(v).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
export const pct = (v?: number | null) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`)
