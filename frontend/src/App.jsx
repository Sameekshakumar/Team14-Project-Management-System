import { useEffect, useState } from 'react'
import Board from './Board.jsx'
import { api, tokens } from './api.js'

/**
 * Three primary screens, which keeps task creation inside the NFR-003 budget
 * of four: sign in -> workspace & project dashboard -> board (create and
 * assign a task inline).
 */
export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(Boolean(tokens.access))
  const [project, setProject] = useState(null)
  const [workspaceId, setWorkspaceId] = useState(null)

  // Resume an existing session on reload rather than forcing a fresh login.
  useEffect(() => {
    if (!tokens.access) return
    api.me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setChecking(false))
  }, [])

  function signOut() {
    api.logout()
    setUser(null)
    setProject(null)
    setWorkspaceId(null)
  }

  if (checking) {
    return <main className="page"><p className="subheading">Restoring session…</p></main>
  }

  if (!user) return <AuthScreen onSignedIn={setUser} />

  if (project) {
    return (
      <main className="page wide">
        <TopBar email={user.email} onSignOut={signOut} />
        <Board project={project} workspaceId={workspaceId} onBack={() => setProject(null)} />
      </main>
    )
  }

  return (
    <main className="page wide">
      <TopBar email={user.email} onSignOut={signOut} />
      <Dashboard
        onOpenProject={(openedProject, openedWorkspaceId) => {
          setWorkspaceId(openedWorkspaceId)
          setProject(openedProject)
        }}
      />
    </main>
  )
}

function TopBar({ email, onSignOut }) {
  return (
    <div className="topbar">
      <div className="brand-mark small">T14</div>
      <span className="topbar-email">{email}</span>
      <button className="link-button" onClick={onSignOut}>Sign out</button>
    </div>
  )
}

function AuthScreen({ onSignedIn }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const signedIn = mode === 'register'
        ? await api.register(email, password)
        : await api.login(email, password)
      onSignedIn(signedIn)
    } catch (error) {
      setMessage(error.message || 'Could not connect to the backend.')
    } finally {
      setBusy(false)
    }
  }

  function switchMode(next) {
    setMode(next)
    setMessage('')
  }

  return (
    <main className="page">
      <section className="panel">
        <div className="brand-mark">T14</div>
        <p className="eyebrow">PROJECT MANAGEMENT SYSTEM</p>
        <h1>{mode === 'register' ? 'Create your account' : 'Welcome back'}</h1>
        <p className="subheading">
          {mode === 'register'
            ? 'Register to join your team workspace.'
            : 'Sign in to continue to your workspace.'}
        </p>
        <div className="tabs" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === 'login' ? 'tab active' : 'tab'}
            onClick={() => switchMode('login')}
          >Log in</button>
          <button
            className={mode === 'register' ? 'tab active' : 'tab'}
            onClick={() => switchMode('register')}
          >Register</button>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input
            id="email" type="email" autoComplete="email" required
            value={email} placeholder="you@example.com"
            onChange={e => setEmail(e.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password" type="password" minLength={8} required
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            value={password} placeholder="At least 8 characters"
            onChange={e => setPassword(e.target.value)}
          />
          <button className="submit" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Log in'}
          </button>
        </form>
        {message && <div className="notice error" role="alert">{message}</div>}
        <p className="footnote">
          Your password is sent to your local backend over HTTP for development. Use HTTPS in deployment.
        </p>
      </section>
      <p className="copyright">Team 14 · Project Management System</p>
    </main>
  )
}

function Dashboard({ onOpenProject }) {
  const [workspaces, setWorkspaces] = useState([])
  const [selected, setSelected] = useState(null)
  const [projects, setProjects] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [workspaceName, setWorkspaceName] = useState('')
  const [projectName, setProjectName] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.workspaces()
      .then(list => {
        setWorkspaces(list)
        setSelected(current => current ?? list[0] ?? null)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) {
      setProjects([])
      return
    }
    let active = true
    api.projects(selected.id)
      .then(list => active && setProjects(list))
      .catch(err => active && setError(err.message))
    return () => { active = false }
  }, [selected])

  async function addWorkspace(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const created = await api.createWorkspace(workspaceName)
      setWorkspaces(current => [...current, created])
      setSelected(created)
      setWorkspaceName('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function addProject(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const created = await api.createProject(selected.id, projectName)
      setProjects(current => [...current, created])
      setProjectName('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="subheading">Loading workspaces…</p>

  return (
    <div className="dashboard">
      {error && <div className="notice error" role="alert">{error}</div>}

      <section className="dash-pane">
        <h2>Workspaces</h2>
        {workspaces.length === 0 && <p className="empty">No workspaces yet. Create one to begin.</p>}
        <ul className="pick-list">
          {workspaces.map(workspace => (
            <li key={workspace.id}>
              <button
                className={selected?.id === workspace.id ? 'pick active' : 'pick'}
                onClick={() => setSelected(workspace)}
              >
                {workspace.name}
              </button>
            </li>
          ))}
        </ul>
        <form className="inline-form" onSubmit={addWorkspace}>
          <input
            aria-label="New workspace name" required maxLength={100}
            value={workspaceName} placeholder="New workspace"
            onChange={e => setWorkspaceName(e.target.value)}
          />
          <button className="submit inline" type="submit" disabled={busy}>Create</button>
        </form>
      </section>

      <section className="dash-pane">
        <h2>Projects{selected ? ` in ${selected.name}` : ''}</h2>
        {!selected ? (
          <p className="empty">Select a workspace first.</p>
        ) : (
          <>
            {projects.length === 0 && <p className="empty">No projects yet.</p>}
            <ul className="pick-list">
              {projects.map(item => (
                <li key={item.id}>
                  <button className="pick" onClick={() => onOpenProject(item, selected.id)}>
                    {item.name} <span className="arrow">Open board &rarr;</span>
                  </button>
                </li>
              ))}
            </ul>
            <form className="inline-form" onSubmit={addProject}>
              <input
                aria-label="New project name" required maxLength={100}
                value={projectName} placeholder="New project"
                onChange={e => setProjectName(e.target.value)}
              />
              <button className="submit inline" type="submit" disabled={busy}>Create</button>
            </form>
          </>
        )}
      </section>
    </div>
  )
}
