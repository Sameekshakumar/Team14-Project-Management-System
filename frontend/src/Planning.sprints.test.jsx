import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Planning from './Planning.jsx'
import { api } from './api.js'

jest.mock('./api.js', () => ({ api: {
  backlog: jest.fn(), workspaces: jest.fn(), sprints: jest.fn(),
  createBacklog: jest.fn(), updateTask: jest.fn(), createSprint: jest.fn(),
  assignSprintItems: jest.fn(), removeSprintItem: jest.fn(), startSprint: jest.fn()
} }))

const project = { id: 'project-1', name: 'Demo' }
const item = { id: 'task-1', title: 'Login page', description: '', story_points: 5 }
const sprint = { id: 'sprint-1', name: 'Sprint 2', start_date: '2026-11-01', end_date: '2026-11-14', status: 'Planned', total_story_points: 5, unestimated_count: 0, items: [] }

beforeEach(() => {
  jest.resetAllMocks()
  api.backlog.mockResolvedValue([item])
  api.workspaces.mockResolvedValue([{ id: 'workspace-1', current_user_role: 'Member' }])
  api.sprints.mockResolvedValue([sprint])
})

async function open() {
  render(<Planning project={project} workspaceId="workspace-1" />)
  await screen.findByRole('heading', { name: 'Demo: Backlog' })
}

test('creates a backlog item with a numeric story point estimate', async () => {
  await open()
  fireEvent.change(screen.getByLabelText('Backlog title'), { target: { value: 'New task' } })
  fireEvent.change(screen.getByLabelText('Story points (blank = not estimated)'), { target: { value: '8' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add backlog item' }))
  await waitFor(() => expect(api.createBacklog).toHaveBeenCalledWith('project-1', { title: 'New task', description: '', story_points: 8 }))
  await waitFor(() => expect(screen.getByLabelText('Backlog title')).toHaveValue(''))
})

test('viewer sees content but no planning write controls', async () => {
  api.workspaces.mockResolvedValue([{ id: 'workspace-1', current_user_role: 'Viewer' }])
  await open()
  expect(screen.getByText('Read-only access.')).toBeInTheDocument()
  expect(screen.getByText('Login page')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add backlog item' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Start sprint' })).not.toBeInTheDocument()
})

test('assigns selected item and refreshes sprint membership and total', async () => {
  await open()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Login page' }))
  fireEvent.change(screen.getByLabelText('Destination sprint'), { target: { value: 'sprint-1' } })
  api.backlog.mockResolvedValue([])
  api.sprints.mockResolvedValue([{ ...sprint, total_story_points: 5, items: [{ ...item, status: 'To Do' }] }])
  fireEvent.click(screen.getByRole('button', { name: 'Move selected items' }))
  await waitFor(() => expect(api.assignSprintItems).toHaveBeenCalledWith('sprint-1', ['task-1']))
  expect(await screen.findByText('5 story points · 1 items · 0 unestimated')).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})

test('shows the empty sprint start error returned by the API', async () => {
  api.startSprint.mockRejectedValue(new Error('Assign at least one backlog item before starting the sprint.'))
  await open()
  fireEvent.click(screen.getByRole('button', { name: 'Start sprint' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Assign at least one backlog item')
})

test('creates a dated sprint with selected items', async () => {
  await open()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Login page' }))
  fireEvent.change(screen.getByLabelText('Sprint name'), { target: { value: 'Sprint 3' } })
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-11-15' } })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-11-28' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create sprint with selected items' }))
  await waitFor(() => expect(api.createSprint).toHaveBeenCalledWith({ project: 'project-1', name: 'Sprint 3', start_date: '2026-11-15', end_date: '2026-11-28', item_ids: ['task-1'] }))
  await waitFor(() => expect(screen.getByLabelText('Sprint name')).toHaveValue(''))
})

test('returns an unstarted item to backlog and refreshes totals', async () => {
  api.backlog.mockResolvedValue([])
  api.sprints.mockResolvedValue([{ ...sprint, items: [{ ...item, status: 'To Do' }] }])
  await open()
  api.backlog.mockResolvedValue([item])
  api.sprints.mockResolvedValue([{ ...sprint, total_story_points: 0 }])
  fireEvent.click(screen.getByRole('button', { name: 'Return to backlog' }))
  await waitFor(() => expect(api.removeSprintItem).toHaveBeenCalledWith('sprint-1', 'task-1'))
  expect(await screen.findByRole('checkbox', { name: 'Select Login page' })).toBeInTheDocument()
})

test('starting a sprint refreshes status and removes planning controls for that sprint', async () => {
  api.sprints.mockResolvedValue([{ ...sprint, items: [{ ...item, status: 'To Do' }] }])
  api.backlog.mockResolvedValue([])
  await open()
  api.sprints.mockResolvedValue([{ ...sprint, status: 'Active', items: [{ ...item, status: 'To Do' }] }])
  fireEvent.click(screen.getByRole('button', { name: 'Start sprint' }))
  expect(await screen.findByRole('heading', { name: 'Sprint 2 — Active' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Return to backlog' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Start sprint' })).not.toBeInTheDocument()
})

test('switching project clears selection and reloads the workspace role', async () => {
  const view = render(<Planning project={project} workspaceId="workspace-1" />)
  await screen.findByRole('checkbox', { name: 'Select Login page' })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Login page' }))
  api.workspaces.mockResolvedValue([{ id: 'workspace-2', current_user_role: 'Viewer' }])
  api.backlog.mockResolvedValue([])
  api.sprints.mockResolvedValue([])
  view.rerender(<Planning project={{ id: 'project-2', name: 'Other' }} workspaceId="workspace-2" />)
  expect(screen.getByText('Loading backlog…')).toBeInTheDocument()
  await screen.findByRole('heading', { name: 'Other: Backlog' })
  expect(screen.getByText('Read-only access.')).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Create sprint with selected items' })).not.toBeInTheDocument()
})
