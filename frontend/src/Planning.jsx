import { useEffect, useState } from 'react'
import { api } from './api.js'

export default function Planning({ project, workspaceId }) {
  const [items, setItems] = useState([])
  const [canWrite, setCanWrite] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState({ title: '', description: '', story_points: '' })

  async function load() {
    setItems(await api.backlog(project.id))
  }
  useEffect(() => {
    let active = true
    Promise.all([api.backlog(project.id), api.workspaces()])
      .then(([list, workspaces]) => {
        if (!active) return
        setItems(list)
        const workspace = workspaces.find(w => String(w.id) === String(workspaceId))
        setCanWrite(['Owner', 'Admin', 'Member'].includes(workspace?.current_user_role))
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
    {canWrite && <form onSubmit={e => {
      e.preventDefault()
      run(async () => {
        await api.createBacklog(project.id, { ...draft, story_points: draft.story_points === '' ? null : Number(draft.story_points) })
        setDraft({ title: '', description: '', story_points: '' })
      })
    }}>
      <label>Backlog title<input required maxLength={150} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
      <label>Description<textarea value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label>
      <label>Story points (blank = not estimated)<input type="number" min="0" max="2147483647" step="1" value={draft.story_points} onChange={e => setDraft({ ...draft, story_points: e.target.value })} /></label>
      <button className="submit inline" disabled={busy}>Add backlog item</button>
    </form>}
    {items.length === 0 && <p>No backlog items yet.</p>}
    {items.map(item => <article className="planning-item" key={item.id}>
      <h3>{item.title}</h3><p>{item.description}</p>
      <p>{item.story_points === null ? 'Not estimated' : `${item.story_points} story points`}</p>
      {canWrite && <Estimate key={`${item.id}-${item.story_points}`} item={item} busy={busy} save={value => run(() => api.updateTask(item.id, { story_points: value }))} />}
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
