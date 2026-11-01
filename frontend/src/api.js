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

function accessExpiresSoon(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return !payload.exp || payload.exp * 1000 < Date.now() + 60_000
  } catch {
    return true
  }
}

async function currentSocketToken() {
  if (!tokens.access) return null
  if (accessExpiresSoon(tokens.access) && !(await refreshAccess())) return null
  return tokens.access
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
  projectContext: projectId => request(`/api/projects/${projectId}/context/`),
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
    request(`/api/tasks/${taskId}/`, { method: 'PATCH', body: payload }),
  comments: (taskId) => request(`/api/tasks/${taskId}/comments/`),
  addComment: (taskId, body) => request(`/api/tasks/${taskId}/comments/`, {
    method: 'POST', body: { body }
  }),
  activity: (projectId) => request(`/api/projects/${projectId}/activity/?limit=30`).then(data => data.results ?? data),
  activityPage: projectId => request(`/api/projects/${projectId}/activity/`),
  activityNext: url => {
    const parsed = new URL(url, API_BASE)
    return request(`${parsed.pathname}${parsed.search}`)
  },
  analytics: (projectId, from, to) => {
    const query = new URLSearchParams()
    if (from) query.set('from', from)
    if (to) query.set('to', to)
    return request(`/api/projects/${projectId}/analytics/${query.size ? `?${query}` : ''}`)
  },
  notifications: (unread = false) => request(`/api/notifications/?limit=30${unread ? '&unread=1' : ''}`),
  unreadCount: () => request('/api/notifications/unread-count/'),
  readNotification: (id) => request(`/api/notifications/${id}/read/`, { method: 'POST', body: {} }),
  readAllNotifications: () => request('/api/notifications/read-all/', { method: 'POST', body: {} }),
  searchMembers: (projectId, query) => request(`/api/projects/${projectId}/members/search/?q=${encodeURIComponent(query)}`),
  updateComment: (taskId, commentId, body) => request(`/api/tasks/${taskId}/comments/${commentId}/`, {
    method: 'PATCH', body: { body }
  }),
  deleteComment: (taskId, commentId) => request(`/api/tasks/${taskId}/comments/${commentId}/`, { method: 'DELETE' })
}

/** Opens a socket with authenticated reconnects and an application heartbeat. */
function openSocket(path, onEvent, onStatus = () => {}) {
  let stopped = false
  let attempts = 0
  let socket = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let stableTimer = null
  let generation = 0
  const maxRetries = 10

  async function connect() {
    const currentGeneration = ++generation
    const token = await currentSocketToken()
    if (stopped || currentGeneration !== generation) return
    if (!token) {
      onStatus('auth-expired')
      return
    }
    const wsBase = API_BASE.replace(/^http/, 'ws')
    socket = new WebSocket(`${wsBase}${path}`, ['t14', `bearer.${token}`])
    let lastPongAt = Date.now()
    if (heartbeatTimer) window.clearInterval(heartbeatTimer)
    socket.onopen = () => {
      lastPongAt = Date.now()
      onStatus('connected')
      if (stableTimer) window.clearTimeout(stableTimer)
      stableTimer = window.setTimeout(() => { attempts = 0 }, 15_000)
      heartbeatTimer = window.setInterval(() => {
        if (Date.now() - lastPongAt > 55_000) {
          socket?.close(4000, 'heartbeat timeout')
          return
        }
        if (socket?.readyState === WebSocket.OPEN) {
          try { socket.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() })) }
          catch { socket.close() }
        }
      }, 25_000)
    }
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data)
        if (event.type === 'pong') { lastPongAt = Date.now(); return }
        onEvent(event)
      } catch { /* Ignore malformed frames and keep the socket alive. */ }
    }
    socket.onerror = () => socket?.close()
    socket.onclose = (event) => {
      if (heartbeatTimer) window.clearInterval(heartbeatTimer)
      if (stableTimer) window.clearTimeout(stableTimer)
      if (stopped || currentGeneration !== generation) return
      if ([4401, 4403, 4404, 4429].includes(event.code)) {
        onStatus(({ 4401: 'auth-expired', 4403: 'forbidden', 4404: 'not-found', 4429: 'connection-limit' })[event.code])
        return
      }
      if (attempts >= maxRetries) { onStatus('offline'); return }
      onStatus('reconnecting')
      const baseDelay = Math.min(30_000, 1_000 * (2 ** Math.min(attempts, 5)))
      const delay = Math.round(baseDelay * (0.8 + Math.random() * 0.4))
      attempts += 1
      reconnectTimer = window.setTimeout(() => {
        if (currentGeneration === generation) connect()
      }, delay)
    }
  }

  connect()
  return {
    close() {
      stopped = true
      generation += 1
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (heartbeatTimer) window.clearInterval(heartbeatTimer)
      if (stableTimer) window.clearTimeout(stableTimer)
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, 'view closed')
    },
    reconnect() {
      stopped = false
      attempts = 0
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (heartbeatTimer) window.clearInterval(heartbeatTimer)
      if (stableTimer) window.clearTimeout(stableTimer)
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close(1000, 'manual reconnect')
      generation += 1
      connect()
    }
  }
}

/** Project task socket; callers should reload REST snapshots after a reconnect. */
export function openProjectSocket(projectId, onEvent, onStatus = () => {}) {
  return openSocket(`/ws/projects/${projectId}/board/`, onEvent, onStatus)
}

/** Private notification socket. */
export function openNotificationsSocket(onEvent, onStatus = () => {}) {
  return openSocket('/ws/notifications/', onEvent, onStatus)
}

export const STATUSES = ['Backlog', 'To Do', 'In Progress', 'Done']
