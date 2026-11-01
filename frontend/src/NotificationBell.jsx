import { useEffect, useState } from 'react'
import { api, openNotificationsSocket } from './api.js'

export default function NotificationBell({ onSelect }) {
  const [notifications, setNotifications] = useState([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')

  async function reload() {
    try {
      const [items, count] = await Promise.all([api.notifications(), api.unreadCount()])
      setNotifications(items)
      setUnread(count.unread_count)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    reload()
    const socket = openNotificationsSocket(event => {
      if (event.type === 'notification') reload()
    }, status => {
      if (status === 'connected') reload()
    })
    return () => socket.close()
  }, [])

  async function markRead(id) {
    try {
      await api.readNotification(id)
      setNotifications(current => current.map(item => item.id === id ? { ...item, is_read: true } : item))
      setUnread(count => Math.max(0, count - 1))
    } catch (err) { setError(err.message) }
  }

  async function markAllRead() {
    try {
      await api.readAllNotifications()
      setNotifications(current => current.map(item => ({ ...item, is_read: true })))
      setUnread(0)
    } catch (err) { setError(err.message) }
  }

  return <div className="notification-bell">
    <button className="bell-button" aria-label={`Notifications, ${unread} unread`} aria-expanded={open}
      onClick={() => setOpen(value => !value)}>
      <span aria-hidden="true">♢</span>{unread > 0 && <span className="unread-badge">{unread > 99 ? '99+' : unread}</span>}
    </button>
    {open && <section className="notification-popover" aria-label="Notifications">
      <header><h2>Notifications</h2><button className="link-button" disabled={!unread} onClick={markAllRead}>Mark all read</button></header>
      {error && <p className="notification-error">{error}</p>}
      {notifications.length === 0 ? <p className="empty">You're all caught up.</p> : <ul>
        {notifications.map(item => <li key={item.id} className={item.is_read ? 'read' : ''}>
          <button className="notification-item" onClick={() => { onSelect(item); setOpen(false); if (!item.is_read) markRead(item.id) }}>
            <span>{item.message}</span>
            <small>{item.project_name} · {timeAgo(item.created_at)}</small>
          </button>
        </li>)}
      </ul>}
    </section>}
  </div>
}

function timeAgo(value) {
  const delta = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const units = [['day', 86400], ['hour', 3600], ['minute', 60]]
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, size] of units) if (Math.abs(delta) >= size) return formatter.format(Math.round(delta / size), unit)
  return formatter.format(delta, 'second')
}
