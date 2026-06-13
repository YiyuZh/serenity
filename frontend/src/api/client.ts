export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface DashboardSummary {
  accounts: number
  posts: number
  failed_posts: number
  pending_posts: number
  latest_sync_status: string | null
  latest_sync_started_at: string | null
  sla_violations_24h: number
}

export interface Account {
  id: number
  source: string
  handle: string
  user_id: string | null
  since_id: string | null
  active: boolean
  poll_interval_seconds: number
  last_checked_at: string | null
}

export interface PostListItem {
  id: number
  account_id: number
  post_id: string
  post_type: string
  original_text: string | null
  translated_text: string | null
  fetch_status: string
  media_status: string
  translation_status: string
  push_status: string
  published_at: string | null
  pushed_at: string | null
  error_message: string | null
}

export interface PostDetail extends PostListItem {
  post_url: string
  referenced_post_id: string | null
  conversation_id: string | null
  lang: string | null
  raw_json: Record<string, unknown> | null
  media_assets: Array<Record<string, unknown>>
  translation_jobs: Array<Record<string, unknown>>
  push_logs: Array<Record<string, unknown>>
  task_attempts: Array<Record<string, unknown>>
}

export interface PostEvent {
  event_type: string
  status: string
  message: string | null
  created_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_KEY = 'serenity_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  async login(username: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    })
  },
  summary: () => request<DashboardSummary>('/api/dashboard/summary'),
  accounts: () => request<Account[]>('/api/accounts'),
  triggerSync: (accountId: number) => request(`/api/accounts/${accountId}/sync`, { method: 'POST' }),
  posts: (status?: string) => request<PostListItem[]>(`/api/posts${status ? `?status=${status}` : ''}`),
  post: (id: number) => request<PostDetail>(`/api/posts/${id}`),
  postEvents: (id: number) => request<PostEvent[]>(`/api/posts/${id}/events`),
  retryPost: (id: number) => request(`/api/posts/${id}/retry`, { method: 'POST' }),
  skipPost: (id: number) => request(`/api/posts/${id}/skip`, { method: 'POST' })
}
