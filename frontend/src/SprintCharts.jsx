import { useEffect, useState } from 'react'
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts'
import { api } from './api.js'

export default function SprintCharts({ project }) {
  const [sprints, setSprints] = useState([])
  const [selected, setSelected] = useState('')
  const [velocity, setVelocity] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [list, data] = await Promise.all([api.sprints(project.id), api.projectVelocity(project.id)])
        if (!active) return
        setSprints(list); setVelocity(data); setError('')
        setSelected(current => list.some(s => s.id === current) ? current : (list.find(s => s.status === 'Active')?.id ?? list[0]?.id ?? ''))
      } catch (e) { if (active) setError(e.message) }
      finally { if (active) setLoading(false) }
    }
    load()
    const timer = window.setInterval(load, 15000)
    window.addEventListener('focus', load)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', load) }
  }, [project.id, refresh])

  return <section className="dash-pane sprint-charts">
    <div className="charts-heading"><h2>{project.name}: Sprint charts</h2>
      <button className="submit inline" onClick={() => setRefresh(n => n + 1)}>Refresh charts</button>
    </div>
    <p className="charts-note">Charts refresh every 15 seconds while this tab is open. Story points measure estimated effort, not logged minutes.</p>
    {error && <p className="notice error" role="alert">{error} Previously loaded figures may be out of date.</p>}
    {loading && <p>Loading sprint charts…</p>}
    {!loading && !error && sprints.length === 0 && <p>No sprints yet. Create one in Backlog & sprints.</p>}
    {sprints.length > 0 && <>
      <label className="charts-picker">Sprint
        <select value={selected} onChange={e => setSelected(e.target.value)}>
          {sprints.map(s => <option key={s.id} value={s.id}>{s.name} — {s.status}</option>)}
        </select>
      </label>
      {selected && <Burndown key={`${selected}-${refresh}`} sprintId={selected} />}
    </>}
    {velocity && <section className="chart-section">
      <h3>Velocity</h3>
      <p>Average: <strong>{velocity.average_velocity} completed story points per sprint</strong></p>
      <p className="charts-note">Includes completed sprints only. Values are frozen when you choose Complete sprint in Backlog & sprints.</p>
      {velocity.sprints.length === 0 ? <p>No completed sprints yet.</p> : <>
        <div className="chart-frame" role="img" aria-label="Velocity chart showing completed story points per sprint">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={velocity.sprints} margin={{ top: 12, right: 20, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#354562" strokeDasharray="3 3" />
              <XAxis dataKey="name" stroke="#a6b3c9" /><YAxis allowDecimals={false} stroke="#a6b3c9" />
              <Tooltip contentStyle={{ background: '#11192d', borderColor: '#354562', color: '#fff' }} />
              <Legend /><Bar dataKey="completed_points" name="Completed story points" fill="#a6f0c6" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-table-scroll"><table><caption>Velocity data</caption>
          <thead><tr><th>Sprint</th><th>Committed at start</th><th>Completed at close</th></tr></thead>
          <tbody>{velocity.sprints.map(s => <tr key={s.sprint}><td>{s.name}</td><td>{s.committed_points ?? 'Unknown'}</td><td>{s.completed_points}</td></tr>)}</tbody>
        </table></div>
      </>}
    </section>}
  </section>
}

function Burndown({ sprintId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    async function load() {
      try { const result = await api.sprintBurndown(sprintId); if (active) { setData(result); setError('') } }
      catch (e) { if (active) setError(e.message) }
    }
    load()
    const timer = window.setInterval(load, 15000)
    window.addEventListener('focus', load)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', load) }
  }, [sprintId])
  return <section className="chart-section">
    <h3>Burndown</h3>
    {error && <p className="notice error" role="alert">{error} Previously loaded figures may be out of date.</p>}
    {!data && !error && <p>Loading burndown…</p>}
    {data && <>
      <p><strong>{data.current.remaining_points} remaining story points</strong> · {data.current.completed_points} completed · {data.current.unestimated_count} unestimated tasks</p>
      {data.status === 'Planned' ? <p>Start this sprint to begin recording burndown history.</p> : <>
        <p className="charts-note">History available from {data.history_available_from || 'the first recorded change'}. Earlier actual values are unavailable. Each day shows its latest recorded state; today can change. Unestimated tasks contribute zero points.</p>
        {data.committed_story_points === null && <p className="charts-note">This sprint was already active when reporting was installed. Its original commitment is unknown, so no ideal line is shown.</p>}
        {data.points.length > 0 && <>
          <div className="chart-frame" role="img" aria-label="Burndown chart showing remaining and ideal story points by date">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.points} margin={{ top: 12, right: 20, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#354562" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#a6b3c9" minTickGap={35} /><YAxis allowDecimals={false} stroke="#a6b3c9" />
                <Tooltip contentStyle={{ background: '#11192d', borderColor: '#354562', color: '#fff' }} />
                <Legend />
                <Line type="stepAfter" dataKey="remaining_points" name="Remaining points" stroke="#a6f0c6" strokeWidth={3} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
                <Line type="linear" dataKey="ideal_points" name="Ideal points" stroke="#8ab4ff" strokeDasharray="5 5" dot={false} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <details><summary>View burndown data</summary><div className="chart-table-scroll"><table><caption>Burndown data</caption>
            <thead><tr><th>Date</th><th>Remaining points</th><th>Ideal points</th></tr></thead>
            <tbody>{data.points.map(p => <tr key={p.date}><td>{p.date}</td><td>{p.remaining_points ?? 'Unavailable'}</td><td>{p.ideal_points ?? 'Unavailable'}</td></tr>)}</tbody>
          </table></div></details>
        </>}
      </>}
    </>}
  </section>
}
