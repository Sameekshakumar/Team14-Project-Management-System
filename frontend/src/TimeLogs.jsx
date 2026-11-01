import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function TimeLogs({ project }) {
  const [tasks, setTasks] = useState([])
  const [taskId, setTaskId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setTasks([])
    setTaskId('')
    api.tasks(project.id).then(list => {
      if (!active) return
      setTasks(list)
      setTaskId(list[0]?.id ?? '')
    }).catch(e => active && setError(e.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [project.id])

  const task = tasks.find(item => item.id === taskId)
  return <section className="dash-pane time-pane">
    <h2>{project.name}: Time logs</h2>
    <p className="time-help">Record time in whole minutes. Each entry is saved against the task and your signed-in account.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {loading ? <p>Loading tasks…</p> : tasks.length === 0 && !error ? <p>No tasks yet. Create a task on the Board or in the backlog first.</p> : null}
    {tasks.length > 0 && <label className="time-task-picker">Task
      <select value={taskId} onChange={e => setTaskId(e.target.value)}>
        {tasks.map(item => <option key={item.id} value={item.id}>{item.title} — {item.status}</option>)}
      </select>
    </label>}
    {task && <TaskTimeHistory key={task.id} task={task} />}
  </section>
}

function TaskTimeHistory({ task }) {
  const [summary, setSummary] = useState(null)
  const [minutes, setMinutes] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true
    api.taskTimeEntries(task.id).then(data => active && setSummary(data))
      .catch(e => active && setError(e.message))
    return () => { active = false }
  }, [task.id])

  async function save(event) {
    event.preventDefault()
    if (busy) return
    const value = Number(minutes)
    if (!Number.isInteger(value) || value < 1 || value > 2147483647) {
      setError('Enter a positive whole number of minutes.')
      return
    }
    setBusy(true); setError(''); setSuccess('')
    try {
      const data = await api.logTaskTime(task.id, { minutes: value, note })
      setSummary(data)
      setMinutes(''); setNote(''); setSuccess('Time logged successfully.')
    } catch (e) {
      setError(e.message)
      if (e.status === 403) setSummary(current => current ? { ...current, can_log_time: false } : current)
    } finally { setBusy(false) }
  }

  return <div>
    <p className="time-help">Assigned to: {task.assignee_email || 'Unassigned'}</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!summary && !error && <p>Loading time entries…</p>}
    {summary && <>
      <p className="time-total">Total logged: <strong>{summary.total_minutes} minutes</strong> ({Math.floor(summary.total_minutes / 60)}h {summary.total_minutes % 60}m)</p>
      {summary.can_log_time ? <form className="time-form" onSubmit={save}>
        <label>Minutes spent<input type="number" required min="1" max="2147483647" step="1" value={minutes} disabled={busy} onChange={e => setMinutes(e.target.value)} /></label>
        <label>Note (optional)<textarea maxLength={1000} value={note} disabled={busy} onChange={e => setNote(e.target.value)} placeholder="What did you work on?" /></label>
        <button className="submit inline" disabled={busy}>{busy ? 'Saving…' : 'Log time'}</button>
      </form> : <p className="time-help">Read-only for this task. Only its assignee or workspace Owner can log time; Viewers cannot add entries.</p>}
      {success && <p className="notice success" role="status">{success}</p>}
      <h3>Time history</h3>
      {summary.entries.length === 0 ? <p>No time logged yet.</p> : <ul className="time-history">
        {summary.entries.map(entry => <li key={entry.id}>
          <strong>{entry.minutes} minutes</strong>
          <p>{entry.user_email} · <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time></p>
          {entry.note && <p className="time-note">{entry.note}</p>}
        </li>)}
      </ul>}
    </>}
  </div>
}
