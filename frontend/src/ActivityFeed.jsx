import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function ActivityFeed({ projectId, revision = 0 }) {
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    api.activity(projectId)
      .then(data => {
        if (!active) return
        setItems(data.results)
        setPage(1)
        setHasMore(Boolean(data.next))
        setError('')
      })
      .catch(err => active && setError(err.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [projectId, revision])

  async function loadMore() {
    setLoading(true)
    try {
      const nextPage = page + 1
      const data = await api.activity(projectId, nextPage)
      setItems(current => [...current, ...data.results])
      setPage(nextPage)
      setHasMore(Boolean(data.next))
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  return <section className="activity-feed" aria-label="Project activity">
    <h2>Activity</h2>
    {loading && items.length === 0 && <p className="empty">Loading activity…</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    {!loading && items.length === 0 && !error && <p className="empty">No activity yet.</p>}
    <ol>{items.map(item => <li key={item.id}>
      <strong>{item.actor_email || 'A member'}</strong> {verbLabel(item.verb)}
      {item.task_title && <> · <span>{item.task_title}</span></>}
      <time dateTime={item.created_at}>{relativeTime(item.created_at)}</time>
    </li>)}</ol>
    {hasMore && <button className="submit inline" type="button" disabled={loading} onClick={loadMore}>
      {loading ? 'Loading…' : 'Load more'}
    </button>}
  </section>
}

function verbLabel(verb) {
  return ({ task_created: 'created a task', task_updated: 'updated a task', task_moved: 'moved a task',
    task_assigned: 'assigned a task', task_deleted: 'deleted a task', comment_added: 'commented on a task',
    comment_updated: 'edited a comment', user_mentioned: 'mentioned a member' })[verb] || verb.replaceAll('_', ' ')
}

function relativeTime(value) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(seconds, 'second')
}
