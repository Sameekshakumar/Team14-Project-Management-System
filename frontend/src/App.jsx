import { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export default function App() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [token, setToken] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    setToken('')
    try {
      const endpoint = mode === 'register' ? '/api/auth/register/' : '/api/auth/login/'
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      const data = await response.json()
      if (!response.ok) {
        const detail = data.detail || data.email?.[0] || data.password?.[0] ||
          Object.values(data).flat().join(' ') || 'Request failed.'
        throw new Error(detail)
      }
      setMessage(mode === 'register' ? 'Account created successfully.' : 'Login successful.')
      setToken(data.access)
      // Demo only: keep the token in component state, not localStorage.
    } catch (error) {
      setMessage(error.message || 'Could not connect to the backend.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <section className="panel">
        <div className="brand-mark">T14</div>
        <p className="eyebrow">PROJECT MANAGEMENT SYSTEM</p>
        <h1>{mode === 'register' ? 'Create your account' : 'Welcome back'}</h1>
        <p className="subheading">
          {mode === 'register' ? 'Register to join your team workspace.' : 'Sign in to continue to your workspace.'}
        </p>
        <div className="tabs" role="tablist" aria-label="Authentication mode">
          <button className={mode === 'login' ? 'tab active' : 'tab'} onClick={() => { setMode('login'); setMessage(''); setToken('') }}>Log in</button>
          <button className={mode === 'register' ? 'tab active' : 'tab'} onClick={() => { setMode('register'); setMessage(''); setToken('') }}>Register</button>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} minLength={8} required value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" />
          <button className="submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Log in'}</button>
        </form>
        {message && <div className={token ? 'notice success' : 'notice error'} role="status">{message}</div>}
        {token && <div className="token"><strong>Access token received</strong><p>For this local demo, the token is kept in memory only.</p><code>{token.slice(0, 34)}…</code></div>}
        <p className="footnote">Your password is sent to your local backend over HTTP for development. Use HTTPS in deployment.</p>
      </section>
      <p className="copyright">Team 14 · Authentication · FR-AUTH-01</p>
    </main>
  )
}
