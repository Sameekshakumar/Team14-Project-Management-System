const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// Tokens live in sessionStorage: they survive a page refresh but not a closed
// tab. A real deployment should move them to httpOnly cookies, which page
// scripts cannot read at all.
const ACCESS_KEY = 't14.access'
const REFRESH_KEY = 't14.refresh'

export const tokens = {
  get access() {
    return sessionStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return sessionStorage.getItem(REFRESH_KEY)
  },
  save(access, refresh) {
    if (access) sessionStorage.setItem(ACCESS_KEY, access)
    if (refresh) sessionStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  }
}

/** Turns a DRF error body into a single readable sentence. */
function readError(data, fallback) {
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  const parts = Object.entries(data).map(([field, value]) => {
    const text = Array.isArray(value) ? value.join(' ') : String(value)
    return field === 'non_field_errors' ? text : `${field}: ${text}`
  })
  return parts.join(' ') || fallback
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function refreshAccess() {
  if (!tokens.refresh) return false
  const response = await fetch(`${API_BASE}/api/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: tokens.refresh })
  })
  if (!response.ok) {
    tokens.clear()
    return false
  }
  const data = await response.json()
  tokens.save(data.access, data.refresh)
  return true
}

async function request(path, { method = 'GET', body, auth = true, retry = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  })

  // Access tokens expire after 15 minutes; swap in a fresh one and retry once.
  if (response.status === 401 && auth && retry && (await refreshAccess())) {
    return request(path, { method, body, auth, retry: false })
  }

  if (response.status === 204) return null

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(readError(data, `Request failed (${response.status}).`), response.status)
  }
  return data
}

export const api = {
  async login(email, password) {
    const data = await request('/api/auth/login/', {
      method: 'POST',
      body: { email, password },
      auth: false
    })
    tokens.save(data.access, data.refresh)
    return data.user
  },

  async register(email, password) {
    const data = await request('/api/auth/register/', {
      method: 'POST',
      body: { email, password },
      auth: false
    })
    tokens.save(data.access, data.refresh)
    return data.user
  },

  logout() {
    tokens.clear()
  },

  me: () => request('/api/auth/me/'),

  workspaces: () => request('/api/auth/workspaces/'),
  createWorkspace: (name) => request('/api/auth/workspaces/', { method: 'POST', body: { name } }),
  members: (workspaceId) => request(`/api/auth/workspaces/${workspaceId}/members/`),

  projects: (workspaceId) => request(`/api/workspaces/${workspaceId}/projects/`),
  createProject: (workspaceId, name) =>
    request(`/api/workspaces/${workspaceId}/projects/`, { method: 'POST', body: { name } }),

  tasks: (projectId) => request(`/api/projects/${projectId}/tasks/`),
  createTask: (projectId, payload) =>
    request(`/api/projects/${projectId}/tasks/`, { method: 'POST', body: payload }),
  updateTask: (taskId, payload) =>
    request(`/api/tasks/${taskId}/`, { method: 'PATCH', body: payload })
}

export const STATUSES = ['Backlog', 'To Do', 'In Progress', 'Done']
