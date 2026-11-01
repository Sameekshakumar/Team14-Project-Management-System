import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Planning from './Planning.jsx'
import { api } from './api.js'

jest.mock('./api.js', () => ({ api: {
  backlog: jest.fn(), workspaces: jest.fn(), createBacklog: jest.fn(), updateTask: jest.fn()
} }))
const project = { id: 'project-1', name: 'Demo' }
const item = { id: 'task-1', title: 'Login page', description: '', story_points: 5 }
beforeEach(() => {
  jest.resetAllMocks()
  api.backlog.mockResolvedValue([item])
  api.workspaces.mockResolvedValue([{ id: 'workspace-1', current_user_role: 'Owner' }])
})
async function open() {
  render(<Planning project={project} workspaceId="workspace-1" />)
  await screen.findByRole('heading', { name: 'Demo: Backlog' })
}
test('owner can create an estimated backlog item', async () => {
  await open()
  fireEvent.change(screen.getByLabelText('Backlog title'), { target: { value: 'New task' } })
  fireEvent.change(screen.getByLabelText('Story points (blank = not estimated)'), { target: { value: '8' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add backlog item' }))
  await waitFor(() => expect(api.createBacklog).toHaveBeenCalledWith('project-1', { title: 'New task', description: '', story_points: 8 }))
  await waitFor(() => expect(screen.getByLabelText('Backlog title')).toHaveValue(''))
})
test('viewer sees items but no write controls', async () => {
  api.workspaces.mockResolvedValue([{ id: 'workspace-1', current_user_role: 'Viewer' }])
  await open()
  expect(screen.getByText('Read-only access.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add backlog item' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save estimate' })).not.toBeInTheDocument()
})
test('estimate change is saved and refreshed', async () => {
  await open()
  fireEvent.change(screen.getByLabelText('Story points for Login page'), { target: { value: '8' } })
  api.backlog.mockResolvedValue([{ ...item, story_points: 8 }])
  fireEvent.click(screen.getByRole('button', { name: 'Save estimate' }))
  await waitFor(() => expect(api.updateTask).toHaveBeenCalledWith('task-1', { story_points: 8 }))
  expect(await screen.findByText('8 story points')).toBeInTheDocument()
})
test('blank estimate submits null and zero remains zero', async () => {
  await open()
  fireEvent.change(screen.getByLabelText('Backlog title'), { target: { value: 'Unestimated' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add backlog item' }))
  await waitFor(() => expect(api.createBacklog).toHaveBeenCalledWith('project-1', { title: 'Unestimated', description: '', story_points: null }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Add backlog item' })).toBeEnabled())
  fireEvent.change(screen.getByLabelText('Backlog title'), { target: { value: 'Zero' } })
  fireEvent.change(screen.getByLabelText('Story points (blank = not estimated)'), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add backlog item' }))
  await waitFor(() => expect(api.createBacklog).toHaveBeenCalledWith('project-1', { title: 'Zero', description: '', story_points: 0 }))
  await waitFor(() => expect(screen.getByLabelText('Backlog title')).toHaveValue(''))
})
