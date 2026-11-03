import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import SprintCharts from './SprintCharts.jsx'
import { api } from './api.js'

jest.mock('./api.js', () => ({ api: { sprints: jest.fn(), projectVelocity: jest.fn(), sprintBurndown: jest.fn() } }))
jest.mock('recharts', () => {
  const React = require('react')
  const Container = ({ children }) => React.createElement('div', null, children)
  const Empty = () => null
  return { ResponsiveContainer: Container, LineChart: Container, BarChart: Container,
    Line: Empty, Bar: Empty, XAxis: Empty, YAxis: Empty, CartesianGrid: Empty, Tooltip: Empty, Legend: Empty }
})
const project = { id: 'p1', name: 'Demo' }
const active = { id: 's1', name: 'Sprint 1', status: 'Active' }
const report = { status: 'Active', current: { remaining_points: 8, completed_points: 5, unestimated_count: 1 },
  committed_story_points: 13, history_available_from: '2026-11-01',
  points: [{ date: '2026-11-01', remaining_points: 8, ideal_points: 13 }, { date: '2026-11-02', remaining_points: null, ideal_points: 0 }] }
beforeEach(() => {
  jest.resetAllMocks()
  api.sprints.mockResolvedValue([active])
  api.projectVelocity.mockResolvedValue({ average_velocity: 0, sprints: [] })
  api.sprintBurndown.mockResolvedValue(report)
})
afterEach(() => jest.useRealTimers())

test('renders burndown, data table and empty completed-sprint state', async () => {
  render(<SprintCharts project={project} />)
  expect(await screen.findByText('8 remaining story points')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /Burndown chart/ })).toBeInTheDocument()
  expect(screen.getByText('Unavailable')).toBeInTheDocument()
  expect(screen.getByText('No completed sprints yet.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Complete sprint' })).not.toBeInTheDocument()
})
test('empty project offers instructions without calling burndown', async () => {
  api.sprints.mockResolvedValue([])
  render(<SprintCharts project={project} />)
  expect(await screen.findByText(/No sprints yet/)).toBeInTheDocument()
  expect(api.sprintBurndown).not.toHaveBeenCalled()
})
test('planned sprint prompts start and does not display a history chart', async () => {
  api.sprintBurndown.mockResolvedValue({ ...report, status: 'Planned', points: [] })
  render(<SprintCharts project={project} />)
  expect(await screen.findByText(/Start this sprint/)).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: /Burndown/ })).not.toBeInTheDocument()
})
test('switches the selected sprint and shows unknown legacy commitment', async () => {
  api.sprints.mockResolvedValue([active, { id: 's2', name: 'Legacy', status: 'Active' }])
  render(<SprintCharts project={project} />)
  await screen.findByText('8 remaining story points')
  api.sprintBurndown.mockResolvedValue({ ...report, committed_story_points: null })
  fireEvent.change(screen.getByLabelText('Sprint'), { target: { value: 's2' } })
  expect(await screen.findByText(/original commitment is unknown/)).toBeInTheDocument()
  expect(api.sprintBurndown).toHaveBeenLastCalledWith('s2')
})
test('velocity shows completed points and commitment in an accessible table', async () => {
  api.projectVelocity.mockResolvedValue({ average_velocity: 5, sprints: [{ sprint: 'done1', name: 'Closed sprint', committed_points: 13, completed_points: 5 }] })
  render(<SprintCharts project={project} />)
  expect(await screen.findByText('5 completed story points per sprint')).toBeInTheDocument()
  expect(screen.getByRole('table', { name: 'Velocity data' })).toHaveTextContent('Closed sprint135')
  expect(screen.getByRole('img', { name: /Velocity chart/ })).toBeInTheDocument()
})
test('manual refresh reloads both reports after task changes', async () => {
  render(<SprintCharts project={project} />)
  await screen.findByText('8 remaining story points')
  api.sprintBurndown.mockResolvedValue({ ...report, current: { ...report.current, remaining_points: 3 } })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh charts' }))
  expect(await screen.findByText('3 remaining story points')).toBeInTheDocument()
  expect(api.projectVelocity).toHaveBeenCalledTimes(2)
})
test('API failures are visible and refresh can recover', async () => {
  api.projectVelocity.mockRejectedValue(new Error('Access denied'))
  render(<SprintCharts project={project} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
  api.projectVelocity.mockResolvedValue({ average_velocity: 0, sprints: [] })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh charts' }))
  expect(await screen.findByText('8 remaining story points')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
test('burndown errors are displayed without crashing', async () => {
  api.sprintBurndown.mockRejectedValue(new Error('Could not load burndown'))
  render(<SprintCharts project={project} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load burndown')
})
test('polls at 15 seconds and cleans up on unmount', async () => {
  jest.useFakeTimers()
  const view = render(<SprintCharts project={project} />)
  await act(async () => {})
  const calls = api.sprintBurndown.mock.calls.length
  await act(async () => { jest.advanceTimersByTime(15000) })
  expect(api.sprintBurndown).toHaveBeenCalledTimes(calls + 1)
  view.unmount()
  await act(async () => { jest.advanceTimersByTime(30000) })
  expect(api.sprintBurndown).toHaveBeenCalledTimes(calls + 1)
})
