import { useEffect, useState } from 'react'
import { api } from './api.js'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const COLORS = ['#7c6cf2', '#41a77b', '#e0a43b', '#db6878', '#4d91d0']
const isoDate = date => date.toISOString().slice(0, 10)

export default function AnalyticsDashboard({ projectId }) {
  const today = new Date()
  const [dateTo, setDateTo] = useState(isoDate(today))
  const [dateFrom, setDateFrom] = useState(isoDate(new Date(today.getTime() - 29 * 86400000)))
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    api.analytics(projectId, dateFrom, dateTo)
      .then(result => { if (active) { setData(result); setError('') } })
      .catch(err => { if (active) setError(err.message) })
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [projectId, dateFrom, dateTo])

  return <section className="analytics" aria-label="Project analytics">
    <div className="analytics-heading"><div><h2>Analytics</h2><p className="subheading">Task and collaboration trends</p></div>
      <div className="analytics-dates"><label>From <input type="date" value={dateFrom} max={dateTo} onChange={e => setDateFrom(e.target.value)} /></label>
        <label>To <input type="date" value={dateTo} min={dateFrom} max={isoDate(today)} onChange={e => setDateTo(e.target.value)} /></label></div>
    </div>
    {loading && <p className="empty">Loading analytics…</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    {!loading && data && <>
      <div className="analytics-cards">
        <Metric label="Total tasks" value={data.total_tasks} />
        <Metric label="Completed" value={data.completed_tasks} />
        <Metric label="Overdue" value={data.overdue_tasks} />
        <Metric label="Completion" value={`${data.completion_percent}%`} />
      </div>
      {data.total_tasks === 0 ? <p className="empty">No tasks yet. Add tasks to see project analytics.</p> : <div className="analytics-grid">
        <Chart title="Tasks by status"><ResponsiveContainer width="100%" height={250}><PieChart><Pie data={data.tasks_by_status} dataKey="count" nameKey="status" outerRadius={82} label>{data.tasks_by_status.map((row, i) => <Cell key={row.status} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></Chart>
        <Chart title="Tasks per assignee"><ResponsiveContainer width="100%" height={250}><BarChart data={data.tasks_by_assignee} margin={{ left: 0, right: 12, bottom: 36 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="email" angle={-25} textAnchor="end" interval={0} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Tasks" fill="#7c6cf2" /></BarChart></ResponsiveContainer></Chart>
        <Chart title="Created and completed"><ResponsiveContainer width="100%" height={250}><LineChart data={data.time_series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" minTickGap={24} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="created" stroke="#4d91d0" /><Line type="monotone" dataKey="completed" stroke="#41a77b" /></LineChart></ResponsiveContainer></Chart>
        <Chart title="Comments and activity"><ResponsiveContainer width="100%" height={250}><LineChart data={data.time_series}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" minTickGap={24} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="comments" stroke="#e0a43b" /><Line type="monotone" dataKey="activity" stroke="#db6878" /></LineChart></ResponsiveContainer></Chart>
        <section className="analytics-panel"><h3>Top contributors</h3>{data.top_contributors.length ? <ol>{data.top_contributors.map(person => <li key={person.user_id}>{person.email} <strong>{person.contributions}</strong></li>)}</ol> : <p className="empty">No activity in this project yet.</p>}</section>
        {data.sprint_progress?.length > 0 && <section className="analytics-panel"><h3>Sprint progress</h3><ul>{data.sprint_progress.map(sprint => <li key={sprint.id}>{sprint.name}: {sprint.completed_tasks}/{sprint.total_tasks} tasks complete</li>)}</ul></section>}
      </div>}
    </>}
  </section>
}

function Metric({ label, value }) { return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article> }
function Chart({ title, children }) { return <section className="analytics-panel"><h3>{title}</h3>{children}</section> }
