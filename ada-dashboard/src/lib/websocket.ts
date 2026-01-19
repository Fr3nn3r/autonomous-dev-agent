/**
 * WebSocket client for real-time dashboard updates.
 */

import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = `ws://${window.location.hostname}:8000/ws/events`

export interface WebSocketEvent {
  event: string
  data: Record<string, unknown>
  timestamp: string
}

export interface UseWebSocketOptions {
  onConnect?: () => void
  onDisconnect?: () => void
  onEvent?: (event: WebSocketEvent) => void
  reconnectInterval?: number
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    reconnectInterval = 3000,
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  // Use refs for callbacks to avoid reconnection loops
  const onConnectRef = useRef(options.onConnect)
  const onDisconnectRef = useRef(options.onDisconnect)
  const onEventRef = useRef(options.onEvent)

  // Keep refs up to date
  useEffect(() => {
    onConnectRef.current = options.onConnect
    onDisconnectRef.current = options.onDisconnect
    onEventRef.current = options.onEvent
  })

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      return
    }

    try {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close()
          return
        }
        setIsConnected(true)
        onConnectRef.current?.()
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setIsConnected(false)
        wsRef.current = null
        onDisconnectRef.current?.()

        // Attempt to reconnect
        if (mountedRef.current) {
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent
          setLastEvent(data)
          onEventRef.current?.(data)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to connect WebSocket:', error)

      // Attempt to reconnect
      if (mountedRef.current) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect()
        }, reconnectInterval)
      }
    }
  }, [reconnectInterval])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const sendMessage = useCallback((type: string, data?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }))
    }
  }, [])

  const ping = useCallback(() => {
    sendMessage('ping')
  }, [sendMessage])

  useEffect(() => {
    mountedRef.current = true
    connect()

    // Set up ping interval to keep connection alive
    const pingInterval = setInterval(ping, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(pingInterval)
      disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Empty deps - only run on mount/unmount

  return {
    isConnected,
    lastEvent,
    sendMessage,
    ping,
    reconnect: connect,
    disconnect,
  }
}

/**
 * Subscribe to specific event types.
 * Note: This hook should only be used within a component that also uses
 * useWebSocket, or within a WebSocket context provider. Each call to
 * useWebSocket creates a new connection.
 */
export function useWebSocketEvent(
  eventType: string,
  callback: (data: Record<string, unknown>) => void,
  webSocketHook?: ReturnType<typeof useWebSocket>
) {
  const internalWs = useWebSocket()
  const ws = webSocketHook ?? internalWs
  const callbackRef = useRef(callback)

  useEffect(() => {
    callbackRef.current = callback
  })

  useEffect(() => {
    if (ws.lastEvent?.event === eventType) {
      callbackRef.current(ws.lastEvent.data)
    }
  }, [ws.lastEvent, eventType])
}

export default useWebSocket
