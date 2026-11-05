import { useCallback, useEffect, useRef, useState } from 'react'
import { api, tokens } from './api.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const HEARTBEAT_MS = 25_000
const PONG_TIMEOUT_MS = 10_000
const MAX_RETRIES = 8

/** Reliable authenticated socket with bounded exponential retry and ping/pong. */
export function useReliableSocket(path, onEvent, { enabled = true, onReconnect } = {}) {
  const [status, setStatus] = useState(enabled ? 'connecting' : 'offline')
  const [retryNonce, setRetryNonce] = useState(0)
  const eventRef = useRef(onEvent)
  const reconnectRef = useRef(onReconnect)
  eventRef.current = onEvent
  reconnectRef.current = onReconnect

  const reconnectNow = useCallback(() => {
    setStatus('connecting')
    setRetryNonce(value => value + 1)
  }, [])

  useEffect(() => {
    if (!enabled || !path) { setStatus('offline'); return undefined }
    let stopped = false
    let socket = null
    let retryTimer = null
    let heartbeatTimer = null
    let pongTimer = null
    let connectTimer = null
    let stableTimer = null
    let retries = 0
    let everConnected = false

    function clearTimer(timer) { if (timer) clearTimeout(timer) }
    function connect() {
      if (stopped) return
      setStatus(everConnected ? 'reconnecting' : 'connecting')
      const accessToken = tokens.access
      if (!accessToken) { setStatus('offline'); return }
      const socketUrl = new URL(path, API_BASE)
      socketUrl.protocol = socketUrl.protocol === 'https:' ? 'wss:' : 'ws:'
      try { socket = new WebSocket(socketUrl, ['t14', `bearer.${accessToken}`]) }
      catch { scheduleRetry(); return }

      connectTimer = setTimeout(() => {
        if (socket?.readyState === WebSocket.CONNECTING) socket.close()
      }, 10_000)
      socket.onopen = () => {
        clearTimer(connectTimer)
        setStatus('connected')
        if (everConnected) reconnectRef.current?.()
        everConnected = true
        clearTimer(stableTimer)
        stableTimer = setTimeout(() => { retries = 0 }, 60_000)
        heartbeatTimer = setInterval(() => {
          if (socket?.readyState !== WebSocket.OPEN) return
          clearTimer(pongTimer)
          try { socket.send(JSON.stringify({ type: 'ping' })) }
          catch { socket.close() ; return }
          pongTimer = setTimeout(() => {
            if (socket?.readyState === WebSocket.OPEN) socket.close()
          }, PONG_TIMEOUT_MS)
        }, HEARTBEAT_MS)
      }
      socket.onmessage = message => {
        try {
          const event = JSON.parse(message.data)
          if (event.type === 'pong') { clearTimer(pongTimer); pongTimer = null; return }
          eventRef.current?.(event)
        } catch { /* Ignore malformed messages; the REST snapshot remains authoritative. */ }
      }
      socket.onerror = () => { if (!stopped) setStatus('reconnecting') }
      socket.onclose = event => {
        clearTimer(connectTimer)
        clearTimer(stableTimer)
        clearInterval(heartbeatTimer)
        clearTimer(pongTimer)
        if (stopped) return
        if (event.code === 4401) {
          api.me().then(scheduleRetry).catch(() => setStatus('offline'))
          return
        }
        scheduleRetry()
      }
    }

    function scheduleRetry() {
      if (stopped) return
      clearTimer(retryTimer)
      clearTimer(connectTimer)
      clearInterval(heartbeatTimer)
      clearTimer(pongTimer)
      if (retries >= MAX_RETRIES) { setStatus('offline'); return }
      setStatus('reconnecting')
      const base = Math.min(1000 * (2 ** retries), 30_000)
      const delay = Math.round(base * (0.75 + Math.random() * 0.5))
      retries += 1
      retryTimer = setTimeout(connect, delay)
    }

    connect()
    return () => {
      stopped = true
      clearTimer(retryTimer)
      clearTimer(connectTimer)
      clearTimer(pongTimer)
      clearTimer(stableTimer)
      clearInterval(heartbeatTimer)
      if (socket) {
        socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
        socket.close(1000)
      }
    }
  }, [enabled, path, retryNonce])

  return { status, reconnectNow }
}

/** Subscribe to project task changes; resync from REST after any reconnect. */
export function useProjectSocket(projectId, onEvent, onReconnect) {
  const path = projectId ? `/ws/projects/${projectId}/board/` : null
  return useReliableSocket(path, onEvent, { enabled: Boolean(projectId && tokens.access), onReconnect })
}
