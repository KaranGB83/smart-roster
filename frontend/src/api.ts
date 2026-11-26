const BASE =
  ((import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function messageFrom(status: number, data: unknown): string {
  const detail = (data as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') {
    const info = (data as { info?: string }).info
    return info ? `${detail} (${info})` : detail
  }
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { loc?: unknown[]; msg?: string }
    return `${(first.loc ?? []).slice(1).join('.')}: ${first.msg ?? 'invalid value'}`
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return `Request failed (${status})`
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, null, `Can't reach the API at ${BASE}. Start the backend and check CORS_ORIGINS.`)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data, messageFrom(res.status, data))
  return data as T
}

export const api = {
  base: BASE,
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
}
