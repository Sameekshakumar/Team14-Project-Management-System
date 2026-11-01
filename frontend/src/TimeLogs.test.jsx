import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TimeLogs from './TimeLogs.jsx'
import { api } from './api.js'

jest.mock('./api.js', () => ({ api: {
  tasks: jest.fn(), taskTimeEntries: jest.fn(), logTaskTime: jest.fn()
} }))
const task = { id: 'task-1', title: 'Login page', status: 'To Do', assignee_email: 'member@example.com' }
const summary = { task: 'task-1', total_minutes: 0, can_log_time: true, entries: [] }
const entry = { id: 'entry-1', minutes: 30, note: 'Built form', user_email: 'member@example.com', created_at: '2026-11-01T05:00:00Z' }
beforeEach(() => {
  jest.resetAllMocks()
  api.tasks.mockResolvedValue([task])
  api.taskTimeEntries.mockResolvedValue(summary)
})
async function open() {
  render(<TimeLogs project={{ id: 'project-1', name: 'Demo' }} />)
  await screen.findByText('No time logged yet.')
}

test('saves numeric minutes and note, refreshes total and clears form', async () => {
  await open()
  api.logTaskTime.mockResolvedValue({ ...summary, total_minutes: 30, entries: [entry] })
  fireEvent.change(screen.getByLabelText('Minutes spent'), { target: { value: '30' } })
  fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'Built form' } })
  fireEvent.click(screen.getByRole('button', { name: 'Log time' }))
  await waitFor(() => expect(api.logTaskTime).toHaveBeenCalledWith('task-1', { minutes: 30, note: 'Built form' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Time logged successfully.')
  expect(screen.getByText('Built form')).toBeInTheDocument()
  expect(screen.getByText(/Total logged:/)).toHaveTextContent('30 minutes')
  expect(screen.getByLabelText('Minutes spent')).toHaveValue(null)
})

test('read-only task shows history without a logging form', async () => {
  api.taskTimeEntries.mockResolvedValue({ ...summary, can_log_time: false, total_minutes: 30, entries: [entry] })
  render(<TimeLogs project={{ id: 'p', name: 'Demo' }} />)
  expect(await screen.findByText('Built form')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Log time' })).not.toBeInTheDocument()
  expect(screen.getByText(/Read-only for this task/)).toBeInTheDocument()
})

test('empty project explains how to create tasks', async () => {
  api.tasks.mockResolvedValue([])
  render(<TimeLogs project={{ id: 'p', name: 'Demo' }} />)
  expect(await screen.findByText(/No tasks yet/)).toBeInTheDocument()
  expect(api.taskTimeEntries).not.toHaveBeenCalled()
})

test('switching tasks clears old draft and uses the new task permissions', async () => {
  api.tasks.mockResolvedValue([task, { ...task, id: 'task-2', title: 'Report' }])
  await open()
  fireEvent.change(screen.getByLabelText('Minutes spent'), { target: { value: '45' } })
  api.taskTimeEntries.mockResolvedValue({ ...summary, task: 'task-2', can_log_time: false })
  fireEvent.change(screen.getByLabelText('Task'), { target: { value: 'task-2' } })
  expect(await screen.findByText(/Read-only for this task/)).toBeInTheDocument()
  expect(screen.queryByLabelText('Minutes spent')).not.toBeInTheDocument()
  expect(api.taskTimeEntries).toHaveBeenLastCalledWith('task-2')
})

test('failed save shows the error and preserves input for correction', async () => {
  await open()
  api.logTaskTime.mockRejectedValue(new Error('Please check the submitted fields.'))
  fireEvent.change(screen.getByLabelText('Minutes spent'), { target: { value: '15' } })
  fireEvent.click(screen.getByRole('button', { name: 'Log time' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Please check')
  expect(screen.getByLabelText('Minutes spent')).toHaveValue(15)
  expect(screen.getByText(/Total logged:/)).toHaveTextContent('0 minutes')
})

test('revoked write access removes the form after a 403 response', async () => {
  await open()
  api.logTaskTime.mockRejectedValue(Object.assign(new Error('Only the task assignee can log time.'), { status: 403 }))
  fireEvent.change(screen.getByLabelText('Minutes spent'), { target: { value: '15' } })
  fireEvent.click(screen.getByRole('button', { name: 'Log time' }))
  expect(await screen.findByText(/Read-only for this task/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Log time' })).not.toBeInTheDocument()
})
