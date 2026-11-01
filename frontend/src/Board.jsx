import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openProjectSocket, STATUSES } from './api.js'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

/**
 * FR-TASK-03: tasks grouped into status columns, movable by drag and drop.
 * Uses the native HTML5 drag-and-drop events rather than a drag library, and
 * pairs every drag target with a status <select> so the board stays usable
 * from the keyboard.
 */
export default function Board({ project, workspaceId, onBack, currentUser, notificationTargetId }) {
  const [tasks, setTasks] = useState([])
  const [members, setMembers] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [dragOver, setDragOver] = useState(null)
  const [draft, setDraft] = useState({ title: '', description: '', assignee: '', parent: '', due_date: '', priority: 'Medium' })
  const [saving, setSaving] = useState(false)
  const [activity, setActivity] = useState([])
  const [activityNext, setActivityNext] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [view, setView] = useState('board')
  const [openTaskId, setOpenTaskId] = useState(null)
  const [socketStatus, setSocketStatus] = useState('connecting')
  const [commentRevision, setCommentRevision] = useState(0)
  const socketRef = useRef(null)
  const [dateFrom, setDateFrom] = useState(() => new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10))
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10))

  useEffect(() => {
    let active = true
    setLoading(true)
    Promise.all([api.tasks(project.id), api.members(workspaceId), api.activityPage(project.id), api.notifications()])
      .then(([taskList, memberList, activityPage, notificationList]) => {
        if (!active) return
        setTasks(taskList)
        setMembers(memberList)
        setActivity(activityPage.results)
        setActivityNext(activityPage.next)
        setNotifications(notificationList)
        setError('')
      })
      .catch(err => active && setError(err.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [project.id, workspaceId])

  async function refreshActivity() {
    const page = await api.activityPage(project.id)
    setActivity(page.results)
    setActivityNext(page.next)
  }

  async function loadMoreActivity() {
    if (!activityNext) return
    try {
      const page = await api.activityNext(activityNext)
      setActivity(current => [...current, ...page.results.filter(item => !current.some(existing => existing.id === item.id))])
      setActivityNext(page.next)
    } catch (err) { setError(err.message) }
  }

  useEffect(() => {
    const connection = openProjectSocket(project.id, event => {
      const payload = event.payload || {}
      if ((event.type === 'task_created' || event.type === 'task_updated') && payload.task) {
        setTasks(current => {
          const exists = current.some(task => task.id === payload.task.id)
          return exists
            ? current.map(task => task.id === payload.task.id ? payload.task : task)
            : [...current, payload.task]
        })
      }
      if (event.type === 'task_deleted') setTasks(current => current.filter(task => task.id !== payload.task_id))
      if (['comment_created', 'comment_updated', 'comment_deleted'].includes(event.type)) {
        setCommentRevision(value => value + 1)
        refreshActivity().catch(err => setError(err.message))
      }
      if (event.type === 'activity_created') refreshActivity().catch(err => setError(err.message))
    }, status => {
      setSocketStatus(status)
      if (status === 'connected') {
        // PostgreSQL is authoritative. REST snapshots recover events missed while offline.
        api.tasks(project.id).then(setTasks).catch(err => setError(err.message))
        refreshActivity().catch(err => setError(err.message))
        setCommentRevision(value => value + 1)
      }
    })
    socketRef.current = connection
    return () => {
      connection.close()
      if (socketRef.current === connection) socketRef.current = null
    }
  }, [project.id])

  useEffect(() => {
    if (!notificationTargetId || !tasks.some(task => task.id === notificationTargetId)) return
    setView('board')
    setOpenTaskId(notificationTargetId)
    window.setTimeout(() => document.getElementById(`task-card-${notificationTargetId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
  }, [notificationTargetId, tasks])

  const columns = useMemo(() => {
    // Subtasks are shown on their parent card, not as cards of their own.
    const topLevel = tasks.filter(task => !task.parent)
    return STATUSES.map(status => ({
      status,
      items: topLevel.filter(task => task.status === status)
    }))
  }, [tasks])

  const parentOptions = tasks.filter(task => !task.parent)

  async function moveTask(taskId, status) {
    const task = tasks.find(t => t.id === taskId)
    if (!task || task.status === status) return

    // Optimistic move, rolled back if the server rejects it (e.g. a task with
    // an incomplete dependency cannot become Done).
    setTasks(current => current.map(t => (t.id === taskId ? { ...t, status } : t)))
    setError('')
    try {
      const updated = await api.updateTask(taskId, { status })
      setTasks(current => current.map(t => (t.id === taskId ? updated : t)))
    } catch (err) {
      setTasks(current => current.map(t => (t.id === taskId ? task : t)))
      setError(err.message)
    }
  }

  async function addTask(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = { title: draft.title, description: draft.description }
      payload.priority = draft.priority
      if (draft.assignee) payload.assignee = Number(draft.assignee)
      if (draft.parent) payload.parent = draft.parent
      if (draft.due_date) payload.due_date = draft.due_date
      await api.createTask(project.id, payload)
      // Re-read the list so a new subtask shows up under its parent card.
      setTasks(await api.tasks(project.id))
      setDraft({ title: '', description: '', assignee: '', parent: '', due_date: '', priority: 'Medium' })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="board-screen">
      <header className="board-header">
        <div>
          <button className="link-button" onClick={onBack}>&larr; Projects</button>
          <div className="board-title-row">
            <h1>{project.name}</h1>
            <button className={view === 'board' ? 'tab active' : 'tab'} onClick={() => setView('board')}>Board</button>
            <button className={view === 'analytics' ? 'tab active' : 'tab'} onClick={async () => {
              setView('analytics')
              setAnalyticsLoading(true)
              setError('')
              try { setAnalytics(await api.analytics(project.id, dateFrom, dateTo)) } catch (err) { setError(err.message) }
              finally { setAnalyticsLoading(false) }
            }}>Analytics</button>
          </div>
          {project.description && <p className="subheading">{project.description}</p>}
          <div className="connection-row">
            <p className={`connection-state ${socketStatus}`} role="status">Live updates: {statusLabel(socketStatus)}</p>
            {['offline', 'auth-expired', 'connection-limit', 'forbidden'].includes(socketStatus) &&
              <button className="link-button" onClick={() => socketRef.current?.reconnect()}>Reconnect</button>}
          </div>
        </div>
      </header>

      {error && <div className="notice error" role="alert">{error}</div>}

      <form className="task-form" onSubmit={addTask}>
        <div className="task-form-row">
          <div className="field">
            <label htmlFor="task-title">New task</label>
            <input
              id="task-title"
              required
              maxLength={150}
              value={draft.title}
              placeholder="What needs doing?"
              onChange={e => setDraft({ ...draft, title: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="task-assignee">Assign to</label>
            <select
              id="task-assignee"
              value={draft.assignee}
              onChange={e => setDraft({ ...draft, assignee: e.target.value })}
            >
              <option value="">Unassigned</option>
              {members.map(member => (
                <option key={member.user_id} value={member.user_id}>
                  {member.email} ({member.role})
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="task-parent">Subtask of</label>
            <select
              id="task-parent"
              value={draft.parent}
              onChange={e => setDraft({ ...draft, parent: e.target.value })}
            >
              <option value="">Top-level task</option>
              {parentOptions.map(task => (
                <option key={task.id} value={task.id}>{task.title}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="task-due-date">Due date</label>
            <input id="task-due-date" type="date" value={draft.due_date || ''}
              onChange={e => setDraft({ ...draft, due_date: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="task-priority">Priority</label>
            <select id="task-priority" value={draft.priority}
              onChange={e => setDraft({ ...draft, priority: e.target.value })}>
              {['Low', 'Medium', 'High', 'Critical'].map(priority => <option key={priority}>{priority}</option>)}
            </select>
          </div>
          <button className="submit inline" type="submit" disabled={saving}>
            {saving ? 'Adding…' : 'Add task'}
          </button>
        </div>
      </form>

      {loading ? (
        <p className="subheading">Loading board…</p>
      ) : view === 'analytics' ? (
        <>
          <form className="date-filter" onSubmit={async event => {
            event.preventDefault()
            setAnalyticsLoading(true)
            try { setAnalytics(await api.analytics(project.id, dateFrom, dateTo)); setError('') }
            catch (err) { setError(err.message) }
            finally { setAnalyticsLoading(false) }
          }}>
            <label>From <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
            <label>To <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></label>
            <button className="submit inline" type="submit">Apply range</button>
          </form>
          {analyticsLoading ? <p className="subheading">Loading analytics…</p> : <AnalyticsPanel analytics={analytics} />}
        </>
      ) : (
        <>
        <div className="columns">
          {columns.map(column => (
            <section
              key={column.status}
              className={dragOver === column.status ? 'column drop-target' : 'column'}
              onDragOver={event => { event.preventDefault(); setDragOver(column.status) }}
              onDragLeave={() => setDragOver(null)}
              onDrop={event => {
                event.preventDefault()
                setDragOver(null)
                const taskId = event.dataTransfer.getData('text/plain')
                if (taskId) moveTask(taskId, column.status)
              }}
            >
              <h2>{column.status} <span className="count">{column.items.length}</span></h2>
              {column.items.map(task => (
                <article
                  id={`task-card-${task.id}`}
                  key={task.id}
                  className="card"
                  draggable
                  onDragStart={event => event.dataTransfer.setData('text/plain', task.id)}
                >
                  <h3>{task.title}</h3>
                  {task.description && <p className="card-description">{task.description}</p>}
                  {task.due_date && <p className="task-due">Due {task.due_date}</p>}
                  <div className="chips">
                    <span className={`chip priority-${task.priority?.toLowerCase() || 'medium'}`}>{task.priority || 'Medium'}</span>
                    {task.is_blocked && <span className="chip blocked">Blocked</span>}
                    {task.subtasks.length > 0 && (
                      <span className="chip">{task.subtasks.length} subtask{task.subtasks.length > 1 ? 's' : ''}</span>
                    )}
                    <span className="chip muted">{task.assignee_email || 'Unassigned'}</span>
                  </div>
                  {task.subtasks.length > 0 && (
                    <ul className="subtasks">
                      {task.subtasks.map(subtask => (
                        <li key={subtask.id}>{subtask.title} <em>{subtask.status}</em></li>
                      ))}
                    </ul>
                  )}
                  {/* Keyboard-accessible equivalent of dragging the card. */}
                  <label className="sr-only" htmlFor={`move-${task.id}`}>
                    Move {task.title} to another column
                  </label>
                  <select
                    id={`move-${task.id}`}
                    className="move-select"
                    value={task.status}
                    onChange={event => moveTask(task.id, event.target.value)}
                  >
                    {STATUSES.map(status => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                  <button className="link-button comment-toggle" onClick={() =>
                    setOpenTaskId(current => current === task.id ? null : task.id)
                  }>{openTaskId === task.id ? 'Hide comments' : 'Comments'}</button>
                  {openTaskId === task.id && <TaskComments
                    task={task} projectId={project.id} members={members} currentUser={currentUser}
                    revision={commentRevision}
                    onAdded={() => refreshActivity().catch(err => setError(err.message))}
                  />}
                </article>
              ))}
              {column.items.length === 0 && <p className="empty">Drop a task here</p>}
            </section>
          ))}
        </div>
        <section className="collaboration-grid">
          <div className="dash-pane">
            <h2>Recent activity</h2>
            {activity.length === 0 ? <p className="empty">No activity yet.</p> : (
              <ul className="activity-list">{activity.map(item => <li key={item.id}>
                <strong>{item.actor_email || 'A teammate'}</strong>{' '}
                {item.event_type === 'task_created' ? 'created' : item.event_type === 'comment_added' ? 'commented on' : 'updated'}{' '}
                {item.task_title || item.payload?.task_title || item.payload?.title || 'a task'}
                <time>{new Date(item.created_at).toLocaleString()}</time>
              </li>)}</ul>
            )}
            {activityNext && <button className="link-button" onClick={loadMoreActivity}>Load more activity</button>}
          </div>
          <div className="dash-pane">
            <h2>Notifications</h2>
            {notifications.length === 0 ? <p className="empty">No notifications.</p> : (
              <ul className="activity-list">{notifications.map(item => <li key={item.id} className={item.is_read ? 'read' : ''}>
                {item.message}
                {!item.is_read && <button className="link-button" onClick={async () => {
                  try {
                    await api.readNotification(item.id)
                    setNotifications(current => current.map(note => note.id === item.id ? { ...note, is_read: true } : note))
                  } catch (err) { setError(err.message) }
                }}>Mark read</button>}
                <time>{new Date(item.created_at).toLocaleString()}</time>
              </li>)}</ul>
            )}
          </div>
        </section>
        </>
      )}
    </div>
  )
}

function TaskComments({ task, projectId, members, currentUser, revision, onAdded }) {
  const [comments, setComments] = useState([])
  const [body, setBody] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [editingId, setEditingId] = useState(null)
  const [editBody, setEditBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [menuIndex, setMenuIndex] = useState(0)
  const canManageAll = ['Owner', 'Admin'].includes(members.find(member => member.user_id === currentUser?.id)?.role)

  useEffect(() => {
    api.comments(task.id).then(setComments).catch(err => setError(err.message))
  }, [task.id, revision])

  useEffect(() => {
    const match = body.match(/(?:^|\s)@([^\s@]*)$/)
    if (!match) { setSuggestions([]); return }
    const timer = window.setTimeout(() => {
      api.searchMembers(projectId, match[1]).then(setSuggestions).catch(() => setSuggestions([]))
    }, 180)
    return () => window.clearTimeout(timer)
  }, [body, projectId])

  function selectSuggestion(member) {
    setBody(current => current.replace(/(?:^|\s)@([^\s@]*)$/, (value) => {
      const prefix = value.startsWith(' ') ? ' ' : ''
      return `${prefix}@${member.email} `
    }))
    setSuggestions([])
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const comment = await api.addComment(task.id, body.trim())
      setComments(current => [...current, comment])
      setBody('')
      setSuggestions([])
      onAdded()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <div className="task-comments">
    <h4>Comments</h4>
    {comments.map(comment => <article className="comment" key={comment.id}>
      <div className="comment-meta"><strong>{comment.author_email}</strong><time>{relativeTime(comment.updated_at || comment.created_at)}</time></div>
      {editingId === comment.id ? (
        <form onSubmit={async event => {
          event.preventDefault()
          setBusy(true)
          try {
            const updated = await api.updateComment(task.id, comment.id, editBody)
            setComments(current => current.map(item => item.id === comment.id ? updated : item))
            setEditingId(null)
            onAdded()
          } catch (err) { setError(err.message) }
          finally { setBusy(false) }
        }}>
          <textarea value={editBody} maxLength={5000} onChange={event => setEditBody(event.target.value)} />
          <button className="submit inline" disabled={busy}>Save</button>
          <button className="link-button" type="button" onClick={() => setEditingId(null)}>Cancel</button>
        </form>
      ) : <p>{renderMentions(comment.body)}</p>}
      {comment.mentioned_users?.length > 0 && <small>Mentions: {comment.mentioned_users.map(user => user.email).join(', ')}</small>}
      {(comment.author === currentUser?.id || canManageAll) && editingId !== comment.id && <div className="comment-actions">
        <button className="link-button" onClick={() => { setEditingId(comment.id); setEditBody(comment.body) }}>Edit</button>
        <button className="link-button danger-link" onClick={async () => {
          if (!window.confirm('Delete this comment?')) return
          try {
            await api.deleteComment(task.id, comment.id)
            setComments(current => current.filter(item => item.id !== comment.id))
            onAdded()
          } catch (err) { setError(err.message) }
        }}>Delete</button>
      </div>}
    </article>)}
    <form onSubmit={submit}>
      <label htmlFor={`comment-${task.id}`}>Add a comment</label>
      <textarea id={`comment-${task.id}`} required maxLength={5000} value={body}
        onChange={e => { setBody(e.target.value); setMenuIndex(0) }} placeholder="Write a comment. Type @ to mention a member…" />
      {suggestions.length > 0 && <ul className="mention-suggestions" role="listbox">
        {suggestions.map((member, index) => <li key={member.id}>
          <button type="button" role="option" aria-selected={index === menuIndex} className={index === menuIndex ? 'selected' : ''}
            onMouseDown={event => event.preventDefault()} onClick={() => selectSuggestion(member)}>{member.email}</button>
        </li>)}
      </ul>}
      {error && <p className="notice error">{error}</p>}
      <button className="submit inline" type="submit" disabled={busy}>{busy ? 'Posting…' : 'Post comment'}</button>
    </form>
  </div>
}

function AnalyticsPanel({ analytics }) {
  if (!analytics) return <div className="dash-pane"><p className="empty">No analytics data is available.</p></div>
  return <section className="analytics-panel">
    <div className="metric-grid">
      <article className="metric"><span>Total tasks</span><strong>{analytics.total_tasks}</strong></article>
      <article className="metric"><span>Completed</span><strong>{analytics.completed_tasks} ({analytics.completion_percent}%)</strong></article>
      <article className="metric"><span>Overdue</span><strong>{analytics.overdue_tasks}</strong></article>
      <article className="metric"><span>Unassigned active</span><strong>{analytics.unassigned_active_tasks}</strong></article>
    </div>
    <div className="dash-pane">
      <h2>Workload by member</h2>
      <div className="table-scroll"><table>
        <thead><tr><th>Member</th><th>Active</th><th>Completed</th><th>Overdue</th></tr></thead>
        <tbody>{analytics.workload_distribution.map(member => <tr key={member.user_id}>
          <td>{member.email}</td><td>{member.active_tasks}</td><td>{member.completed_tasks}</td><td>{member.overdue_tasks}</td>
        </tr>)}</tbody>
      </table></div>
    </div>
    <ChartsPanel analytics={analytics} />
    <div className="dash-pane">
      <h2>Top contributors</h2>
      {analytics.top_contributors.length === 0 ? <p className="empty">No activity in this project yet.</p> :
        <ol className="contributor-list">{analytics.top_contributors.map(person =>
          <li key={person.user_id}><span>{person.email}</span><strong>{person.contributions}</strong></li>
        )}</ol>}
    </div>
  </section>
}

function ChartsPanel({ analytics }) {
  const colors = ['#a6f0c6', '#84b7ff', '#f1cc84', '#e993aa', '#b8a1ff']
  const hasTasks = analytics.total_tasks > 0
  return <div className="chart-grid">
    <article className="dash-pane chart-pane">
      <h2>Tasks by status</h2>
      {hasTasks ? <ResponsiveContainer width="100%" height={260}><PieChart>
        <Pie data={analytics.tasks_by_status} dataKey="count" nameKey="status" cx="50%" cy="50%" outerRadius={82} label>
          {analytics.tasks_by_status.map((item, index) => <Cell key={item.status} fill={colors[index % colors.length]} />)}
        </Pie><Tooltip /><Legend />
      </PieChart></ResponsiveContainer> : <p className="empty">No tasks in this date range.</p>}
    </article>
    <article className="dash-pane chart-pane">
      <h2>Tasks by assignee</h2>
      {analytics.tasks_by_assignee.length ? <ResponsiveContainer width="100%" height={260}><BarChart data={analytics.tasks_by_assignee} margin={{ left: -15 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2c3b58" /><XAxis dataKey="email" hide /><YAxis allowDecimals={false} stroke="#8fa5c8" />
        <Tooltip /><Legend /><Bar dataKey="count" name="Tasks" fill="#84b7ff" radius={[5, 5, 0, 0]} />
      </BarChart></ResponsiveContainer> : <p className="empty">No assigned tasks in this project.</p>}
      {analytics.tasks_by_assignee.length > 0 && <ul className="chart-labels">{analytics.tasks_by_assignee.map(item => <li key={item.email}>{item.email}: {item.count}</li>)}</ul>}
    </article>
    <article className="dash-pane chart-pane">
      <h2>Tasks by priority</h2>
      {hasTasks ? <ResponsiveContainer width="100%" height={260}><PieChart>
        <Pie data={analytics.tasks_by_priority} dataKey="count" nameKey="priority" cx="50%" cy="50%" outerRadius={82} label>
          {analytics.tasks_by_priority.map((item, index) => <Cell key={item.priority} fill={colors[index % colors.length]} />)}
        </Pie><Tooltip /><Legend />
      </PieChart></ResponsiveContainer> : <p className="empty">No tasks in this project.</p>}
    </article>
    <article className="dash-pane chart-pane wide-chart">
      <h2>Tasks created and completed per day</h2>
      {analytics.time_series.some(day => day.created || day.completed) ? <ResponsiveContainer width="100%" height={280}><LineChart data={analytics.time_series}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2c3b58" /><XAxis dataKey="date" tick={{ fill: '#8fa5c8', fontSize: 10 }} minTickGap={25} />
        <YAxis allowDecimals={false} stroke="#8fa5c8" /><Tooltip /><Legend />
        <Line type="monotone" dataKey="created" name="Created" stroke="#84b7ff" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="completed" name="Completed" stroke="#a6f0c6" strokeWidth={2} dot={false} />
      </LineChart></ResponsiveContainer> : <p className="empty">No task changes in this date range.</p>}
    </article>
    <article className="dash-pane chart-pane wide-chart">
      <h2>Comment and activity volume</h2>
      {analytics.time_series.some(day => day.comments || day.activity) ? <ResponsiveContainer width="100%" height={260}><LineChart data={analytics.time_series}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2c3b58" /><XAxis dataKey="date" tick={{ fill: '#8fa5c8', fontSize: 10 }} minTickGap={25} />
        <YAxis allowDecimals={false} stroke="#8fa5c8" /><Tooltip /><Legend />
        <Line type="monotone" dataKey="comments" name="Comments" stroke="#f1cc84" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="activity" name="Activity" stroke="#e993aa" strokeWidth={2} dot={false} />
      </LineChart></ResponsiveContainer> : <p className="empty">No comments or activity in this date range.</p>}
    </article>
  </div>
}

function renderMentions(text) {
  return text.split(/(@[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/gi).map((part, index) =>
    part.startsWith('@') ? <mark key={index}>{part}</mark> : part
  )
}

function relativeTime(value) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const units = [['year', 31536000], ['month', 2592000], ['week', 604800], ['day', 86400], ['hour', 3600], ['minute', 60]]
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, size] of units) if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  return formatter.format(seconds, 'second')
}

function statusLabel(status) {
  return ({ connected: 'Connected', connecting: 'Connecting', reconnecting: 'Reconnecting', offline: 'Offline',
    'auth-expired': 'Sign in again', forbidden: 'Access revoked', 'not-found': 'Project unavailable',
    'connection-limit': 'Connection limit reached' })[status] || 'Offline'
}
