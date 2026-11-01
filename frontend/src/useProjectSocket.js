import { useEffect } from 'react'
import { tokens } from './api.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

/** Subscribe to task changes for one project and clean up on navigation. */
export function useProjectSocket(projectId, onEvent) {
  useEffect(() => {
    const accessToken = tokens.access
    if (!projectId || !accessToken) return undefined

    const socketUrl = new URL(`/ws/projects/${projectId}/board/`, API_BASE)
    socketUrl.protocol = socketUrl.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(socketUrl, ['t14', `bearer.${accessToken}`])
    socket.onmessage = message => {
      try {
        onEvent(JSON.parse(message.data))
      } catch {
        // Ignore malformed messages; the next REST load remains authoritative.
      }
    }

    return () => {
      socket.onmessage = null
      socket.close()
    }
  }, [projectId, onEvent])
}
