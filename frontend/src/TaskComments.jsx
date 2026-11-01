import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'

export default function TaskComments({ projectId, task, currentUserId, canManageAll, refreshRevision }) {
  const [comments, setComments] = useState([])
  const [body, setBody] = useState('')
  const [editing, setEditing] = useState(null)
  const [editBody, setEditBody] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef(null)

  const reload = useCallback(() => {
    api.comments(task.id).then(setComments).catch(err => setError(err.message))
  }, [task.id])

  useEffect(() => { reload() }, [reload, refreshRevision])

  const query = (() => {
    const prefix = body.slice(0, input.current?.selectionStart ?? body.length)
    return /(?:^|\s)@([^\s@]*)$/.exec(prefix)?.[1] ?? null
  })()

  useEffect(() => {
    if (query === null) { setSuggestions([]); return undefined }
    const timer = window.setTimeout(() => {
      api.searchProjectMembers(projectId, query)
        .then(setSuggestions)
        .catch(() => setSuggestions([]))
    }, 120)
    return () => window.clearTimeout(timer)
  }, [projectId, query])

  function selectMention(member) {
    const caret = input.current?.selectionStart ?? body.length
    const before = body.slice(0, caret)
    const match = /(?:^|\s)@([^\s@]*)$/.exec(before)
    if (!match) return
    const start = caret - match[0].length + (match[0].startsWith(' ') ? 1 : 0)
    const next = `${body.slice(0, start)}@${member.email} ${body.slice(caret)}`
    setBody(next)
    setSuggestions([])
    requestAnimationFrame(() => {
      input.current?.focus()
      const position = start + member.email.length + 2
      input.current?.setSelectionRange(position, position)
    })
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const created = await api.createComment(task.id, body)
      setComments(current => [...current, created])
      setBody('')
      setSuggestions([])
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  async function saveEdit(comment) {
    setBusy(true)
    setError('')
    try {
      const updated = await api.updateComment(task.id, comment.id, editBody)
      setComments(current => current.map(item => item.id === comment.id ? updated : item))
      setEditing(null)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  async function remove(comment) {
    if (!window.confirm('Delete this comment?')) return
    try {
      await api.deleteComment(task.id, comment.id)
      setComments(current => current.filter(item => item.id !== comment.id))
    } catch (err) { setError(err.message) }
  }

  return <section className="comment-panel" aria-label={`Comments for ${task.title}`}>
    <h4>Comments</h4>
    {comments.map(comment => {
      const canManage = String(comment.author) === String(currentUserId) || canManageAll
      return <article className="comment" key={comment.id}>
        <header><strong>{comment.author_email || 'Former member'}</strong><time dateTime={comment.created_at}>{relativeTime(comment.created_at)}</time></header>
        {editing === comment.id ? <form onSubmit={event => { event.preventDefault(); saveEdit(comment) }}>
          <textarea value={editBody} maxLength={5000} onChange={event => setEditBody(event.target.value)} />
          <button className="submit inline" disabled={busy}>Save</button>
          <button className="link-button" type="button" onClick={() => setEditing(null)}>Cancel</button>
        </form> : <p>{renderMentions(comment.body)}</p>}
        {comment.mentioned_users?.length > 0 && <small>Mentions: {comment.mentioned_users.map(user => user.email).join(', ')}</small>}
        {canManage && editing !== comment.id && <div className="comment-actions">
          <button className="link-button" type="button" onClick={() => { setEditing(comment.id); setEditBody(comment.body) }}>Edit</button>
          <button className="link-button danger-link" type="button" onClick={() => remove(comment)}>Delete</button>
        </div>}
      </article>
    })}
    <form onSubmit={submit}>
      <label htmlFor={`comment-${task.id}`}>Add a comment</label>
      <textarea ref={input} id={`comment-${task.id}`} required maxLength={5000} value={body}
        onChange={event => { setBody(event.target.value); setError('') }} placeholder="Write a comment. Type @ to mention a member…" />
      {suggestions.length > 0 && <ul className="mention-suggestions" role="listbox">
        {suggestions.map(member => <li key={member.id}><button type="button" role="option"
          onMouseDown={event => event.preventDefault()} onClick={() => selectMention(member)}>{member.email}</button></li>)}
      </ul>}
      {error && <p className="notice error" role="alert">{error}</p>}
      <button className="submit inline" type="submit" disabled={busy || !body.trim()}>{busy ? 'Posting…' : 'Post comment'}</button>
    </form>
  </section>
}

function renderMentions(body) {
  return body.split(/(@[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/gi).map((part, index) =>
    part.startsWith('@') ? <mark key={index}>{part}</mark> : part
  )
}

function relativeTime(value) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(seconds, 'second')
}
