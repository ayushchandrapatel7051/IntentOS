/**
 * useWebSocket — Custom React hook for WebSocket with auto-reconnect
 */

import { useRef, useEffect, useState, useCallback } from 'react'

const RECONNECT_BASE_DELAY = 1000
const MAX_RECONNECT_DELAY = 30000
const MAX_RECONNECT_ATTEMPTS = 20

function useWebSocket(url, onMessage) {
  const wsRef = useRef(null)
  const [readyState, setReadyState] = useState(3) // CLOSED
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const urlRef = useRef(url)
  const onMessageRef = useRef(onMessage)

  // Keep refs updated
  useEffect(() => { urlRef.current = url }, [url])
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])

  const connect = useCallback(() => {
    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close()
    }

    try {
      const ws = new WebSocket(urlRef.current)
      wsRef.current = ws

      ws.onopen = () => {
        setReadyState(ws.readyState)
        reconnectAttemptRef.current = 0
        console.log('[WS] Connected to', urlRef.current)
      }

      ws.onmessage = (event) => {
        if (onMessageRef.current) {
          onMessageRef.current(event)
        }
      }

      ws.onclose = (event) => {
        setReadyState(3)
        console.log('[WS] Disconnected:', event.code, event.reason)

        // Auto-reconnect with exponential backoff
        if (reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(
            RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttemptRef.current),
            MAX_RECONNECT_DELAY
          )
          console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current + 1})`)
          reconnectTimerRef.current = setTimeout(() => {
            reconnectAttemptRef.current++
            connect()
          }, delay)
        }
      }

      ws.onerror = (error) => {
        console.error('[WS] Error:', error)
      }
    } catch (e) {
      console.error('[WS] Connection failed:', e)
      setReadyState(3)
    }
  }, [])

  // Connect on mount
  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message)
    } else {
      console.warn('[WS] Cannot send — not connected')
    }
  }, [])

  return {
    sendMessage,
    readyState,
    reconnect: connect,
  }
}

export default useWebSocket
