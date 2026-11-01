import { useEffect, useState } from 'react'
import { api, tokens } from './api.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export default function NotificationBell() {
  const [count, setCount] = useState(0)
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)

  async function refresh() {
    const [countData, page] = await Promise.all([api.unreadCount(), api.notifications()])
    setCount(countData.count)
    setItems(page.results)
  }

  useEffect(() => {
    refresh().catch(() => {})
    const token = tokens.access
    if (!token) return undefined
    const url = new URL('/ws/notifications/', API_BASE)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(url, ['t14', `bearer.${token}`])
    socket.onmessage = message => {
      try {
        if (JSON.parse(message.data).type === 'notification') refresh().catch(() => {})
      } catch { /* Ignore malformed messages. */ }
    }
    return () => socket.close()
  }, [])

  async function openNotification(notification) {
    try {
      await api.markNotificationRead(notification.id)
      await refresh()
      setOpen(false)
      window.dispatchEvent(new CustomEvent('notification:navigate', {
        detail: { projectId: notification.project, taskId: notification.task },
      }))
    } catch { /* The list remains available if marking read fails. */ }
  }

  async function markAllRead() {
    try { await api.markAllNotificationsRead(); await refresh() } catch { /* keep current badge */ }
  }

  return <div className="notification-bell">
    <button className="link-button" type="button" aria-expanded={open} aria-label={`Notifications, ${count} unread`}
      onClick={() => setOpen(value => !value)}>
      Notifications {count > 0 && <span className="notification-count">{count > 99 ? '99+' : count}</span>}
    </button>
    {open && <section className="notification-menu" aria-label="Notifications">
      <header><strong>Notifications</strong>{count > 0 && <button className="link-button" onClick={markAllRead}>Mark all read</button>}</header>
      {items.length === 0 ? <p className="empty">You’re all caught up.</p> : items.map(item =>
        <button className={item.is_read ? 'notification-item' : 'notification-item unread'} key={item.id}
          onClick={() => openNotification(item)}>
          <span>{item.message}</span>
          <small>{item.project_name}{item.task_title ? ` · ${item.task_title}` : ''}</small>
        </button>
      )}
    </section>}
  </div>
}
