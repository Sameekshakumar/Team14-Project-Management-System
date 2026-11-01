import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, STATUSES } from './api.js'
import { useProjectSocket } from './useProjectSocket.js'
import TaskComments from './TaskComments.jsx'
import ActivityFeed from './ActivityFeed.jsx'

/**
 * FR-TASK-03: tasks grouped into status columns, movable by drag and drop.
 * Uses the native HTML5 drag-and-drop events rather than a drag library, and
 * pairs every drag target with a status <select> so the board stays usable
 * from the keyboard.
 */
export default function Board({ project, workspaceId, userId, onBack }) {
  const [tasks, setTasks] = useState([])
  const [members, setMembers] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [dragOver, setDragOver] = useState(null)
  const [draft, setDraft] = useState({ title: '', description: '', assignee: '', parent: '' })
  const [saving, setSaving] = useState(false)
  const [openCommentsTask, setOpenCommentsTask] = useState(null)
  const [commentRevision, setCommentRevision] = useState(0)
  const [activityRevision, setActivityRevision] = useState(0)
  const [showActivity, setShowActivity] = useState(false)
  const [notificationTaskId, setNotificationTaskId] = useState(null)

  const refreshTasks = useCallback(() => {
    api.tasks(project.id).then(setTasks).catch(err => setError(err.message))
  }, [project.id])

  const handleSocketEvent = useCallback(event => {
    if (event.type === 'activity_created') {
      setActivityRevision(value => value + 1)
      return
    }
    if (event.type?.startsWith('comment_')) {
      if (String(event.actor) !== String(userId)) setCommentRevision(value => value + 1)
      return
    }
    // REST responses already update the initiating user's board. Ignore its
    // echo; other members refresh from the canonical task endpoint.
    if (String(event.actor) !== String(userId)) refreshTasks()
  }, [refreshTasks, userId])

  useProjectSocket(project.id, handleSocketEvent)

  useEffect(() => {
    function openTask(event) { setNotificationTaskId(event.detail.taskId) }
    window.addEventListener('notification:open-task', openTask)
    return () => window.removeEventListener('notification:open-task', openTask)
  }, [])

  useEffect(() => {
    if (!notificationTaskId || !tasks.some(task => String(task.id) === String(notificationTaskId))) return
    setOpenCommentsTask(notificationTaskId)
    document.getElementById(`task-card-${notificationTaskId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setNotificationTaskId(null)
  }, [notificationTaskId, tasks])

  useEffect(() => {
    let active = true
    setLoading(true)
    Promise.all([api.tasks(project.id), api.members(workspaceId)])
      .then(([taskList, memberList]) => {
        if (!active) return
        setTasks(taskList)
        setMembers(memberList)
        setError('')
      })
      .catch(err => active && setError(err.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [project.id, workspaceId])

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
      if (draft.assignee) payload.assignee = Number(draft.assignee)
      if (draft.parent) payload.parent = draft.parent
      await api.createTask(project.id, payload)
      // Re-read the list so a new subtask shows up under its parent card.
      setTasks(await api.tasks(project.id))
      setDraft({ title: '', description: '', assignee: '', parent: '' })
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
          <h1>{project.name}</h1>
          {project.description && <p className="subheading">{project.description}</p>}
        </div>
      </header>

      <div className="activity-toggle-row">
        <button className="link-button" type="button" aria-expanded={showActivity}
          onClick={() => setShowActivity(value => !value)}>
          {showActivity ? 'Hide activity' : 'Project activity'}
        </button>
      </div>
      {showActivity && <ActivityFeed projectId={project.id} revision={activityRevision} />}

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
          <button className="submit inline" type="submit" disabled={saving}>
            {saving ? 'Adding…' : 'Add task'}
          </button>
        </div>
      </form>

      {loading ? (
        <p className="subheading">Loading board…</p>
      ) : (
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
                  <div className="chips">
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
                  <button className="link-button comment-toggle" type="button"
                    onClick={() => setOpenCommentsTask(current => current === task.id ? null : task.id)}>
                    {openCommentsTask === task.id ? 'Hide comments' : 'Comments'}
                  </button>
                  {openCommentsTask === task.id && <TaskComments
                    projectId={project.id}
                    task={task}
                    currentUserId={userId}
                    canManageAll={members.some(member => String(member.user_id) === String(userId) && ['Owner', 'Admin'].includes(member.role))}
                    refreshRevision={commentRevision}
                  />}
                </article>
              ))}
              {column.items.length === 0 && <p className="empty">Drop a task here</p>}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
