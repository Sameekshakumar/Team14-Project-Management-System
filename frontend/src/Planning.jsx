import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function Planning({ project, workspaceId }) {
  return <PlanningContent key={`${workspaceId}-${project.id}`} project={project} workspaceId={workspaceId} />
}

function PlanningContent({ project, workspaceId }) {
  const [items, setItems] = useState([])
  const [sprints, setSprints] = useState([])
  const [selected, setSelected] = useState([])
  const [target, setTarget] = useState('')
  const [sprintDraft, setSprintDraft] = useState({ name: '', start_date: '', end_date: '' })
  const [canWrite, setCanWrite] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState({ title: '', description: '', story_points: '' })

  async function load() {
    const [backlog, sprintList] = await Promise.all([api.backlog(project.id), api.sprints(project.id)])
    setItems(backlog); setSprints(sprintList)
    setTarget(current => sprintList.some(s => s.id === current && s.status === 'Planned') ? current : '')
    setSelected(current => current.filter(id => backlog.some(item => item.id === id)))
  }
  useEffect(() => {
    let active = true
    Promise.all([api.backlog(project.id), api.workspaces(), api.sprints(project.id)])
      .then(([list, workspaces, sprintList]) => {
        if (!active) return
        setItems(list)
        setSprints(sprintList)
        const workspace = workspaces.find(w => String(w.id) === String(workspaceId))
        if (!workspace?.current_user_role) throw new Error('Workspace role could not be loaded. Reopen the project or sign in again.')
        setCanWrite(['Owner', 'Admin', 'Member'].includes(workspace.current_user_role))
      })
      .catch(e => active && setError(e.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [project.id, workspaceId])

  async function run(action) {
    setBusy(true); setError('')
    try { await action(); await load() } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  if (loading) return <p>Loading backlog…</p>
  return <section className="dash-pane planning-pane">
    <h2>{project.name}: Backlog</h2>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!canWrite && <p>Read-only access.</p>}
    {canWrite && <div className="planning-forms"><form className="planning-create-form" onSubmit={e => {
      e.preventDefault()
      run(async () => {
        await api.createBacklog(project.id, { ...draft, story_points: draft.story_points === '' ? null : Number(draft.story_points) })
        setDraft({ title: '', description: '', story_points: '' })
      })
    }}>
      <h3>Add a backlog item</h3>
      <label>Backlog title<input required maxLength={150} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
      <label>Description<textarea value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label>
      <label>Story points (blank = not estimated)<input type="number" min="0" max="2147483647" step="1" value={draft.story_points} onChange={e => setDraft({ ...draft, story_points: e.target.value })} /></label>
      <button className="submit inline" disabled={busy}>Add backlog item</button>
    </form>
      <form className="planning-create-form" onSubmit={e => {
        e.preventDefault()
        run(async () => {
          await api.createSprint({ ...sprintDraft, project: project.id, item_ids: selected })
          setSprintDraft({ name: '', start_date: '', end_date: '' }); setSelected([])
        })
      }}>
        <h3>Create a sprint</h3>
        <label>Sprint name<input required maxLength={100} value={sprintDraft.name} onChange={e => setSprintDraft({ ...sprintDraft, name: e.target.value })} /></label>
        <label>Start date<input required type="date" value={sprintDraft.start_date} onChange={e => setSprintDraft({ ...sprintDraft, start_date: e.target.value })} /></label>
        <label>End date<input required type="date" min={sprintDraft.start_date} value={sprintDraft.end_date} onChange={e => setSprintDraft({ ...sprintDraft, end_date: e.target.value })} /></label>
        <p className="planning-hint">{selected.length} backlog item(s) selected below. You can also create an empty planned sprint and assign items later.</p>
        <button className="submit inline" disabled={busy}>Create sprint with selected items</button>
      </form>
    </div>}
    <h3 className="planning-section-title">Unassigned backlog</h3>
    {canWrite && <form className="inline-form planning-assignment" onSubmit={e => {
        e.preventDefault()
        run(async () => { await api.assignSprintItems(target, selected); setSelected([]) })
      }}>
        <select aria-label="Destination sprint" disabled={busy} required value={target} onChange={e => setTarget(e.target.value)}>
          <option value="">Choose a planned sprint</option>
          {sprints.filter(s => s.status === 'Planned').map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button className="submit inline" disabled={busy || selected.length === 0 || !sprints.some(s => s.id === target && s.status === 'Planned')}>Move selected items</button>
      </form>
    }
    {items.length === 0 && <p>No backlog items yet.</p>}
    {items.map(item => <article className="planning-item" key={item.id}>
      {canWrite && <label className="planning-selection"><input  type="checkbox" disabled={busy} checked={selected.includes(item.id)} onChange={e => setSelected(current => e.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} /> Select {item.title}</label>}
      <h3>{item.title}</h3><p>{item.description}</p>
      <p>{item.story_points === null ? 'Not estimated' : `${item.story_points} story points`}</p>
      {canWrite && <Estimate key={`${item.id}-${item.story_points}`} item={item} busy={busy} save={value => run(() => api.updateTask(item.id, { story_points: value }))} />}
    </article>)}
    <h3 className="planning-section-title">Sprints</h3>
    {sprints.length === 0 && <p>No sprints yet.</p>}
    {sprints.map(sprint => <article className="planning-item" key={sprint.id}>
      <h3>{sprint.name} — {sprint.status}</h3>
      <p>{sprint.start_date} to {sprint.end_date}</p>
      <p>{sprint.total_story_points} story points · {sprint.items.length} items · {sprint.unestimated_count} unestimated</p>
      {sprint.items.map(item => <div className="planning-sprint-task" key={item.id}>
        <p>{item.title} — {item.status} — {item.story_points ?? 'Unestimated'} points</p>
        {canWrite && <Estimate key={`${item.id}-${item.story_points}`} item={item} busy={busy} save={value => run(() => api.updateTask(item.id, { story_points: value }))} />}
        {canWrite && sprint.status === 'Planned' && ['Backlog', 'To Do'].includes(item.status) && <button className="link-button" disabled={busy} onClick={() => run(() => api.removeSprintItem(sprint.id, item.id))}>Return to backlog</button>}
      </div>)}
      {canWrite && sprint.status === 'Planned' && <button className="submit inline" disabled={busy} onClick={() => run(() => api.startSprint(sprint.id))}>Start sprint</button>}
      {canWrite && sprint.status === 'Active' && <button className="submit inline" disabled={busy} onClick={() => {
        if (window.confirm('Complete this sprint? Completed story points will be frozen for velocity. Unfinished tasks stay in this sprint.')) {
          run(() => api.completeSprint(sprint.id))
        }
      }}>Complete sprint</button>}
      {sprint.status === 'Completed' && <p>Completed velocity: {sprint.completed_story_points ?? 0} story points (frozen at completion).</p>}
    </article>)}
  </section>
}

function Estimate({ item, busy, save }) {
  const [points, setPoints] = useState(item.story_points ?? '')
  return <form className="inline-form" onSubmit={e => { e.preventDefault(); save(points === '' ? null : Number(points)) }}>
    <input aria-label={`Story points for ${item.title}`} type="number" min="0" max="2147483647" step="1" value={points} onChange={e => setPoints(e.target.value)} />
    <button className="submit inline" disabled={busy}>Save estimate</button>
  </form>
}
