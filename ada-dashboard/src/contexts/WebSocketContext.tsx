import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const WS_URL = `ws://${window.location.hostname}:8000/ws/events`

export interface WebSocketEvent {
  event: string
  data: Record<string, unknown>
  timestamp: string
}

type EventHandler = (data: Record<string, unknown>) => void

interface WebSocketContextValue {
  isConnected: boolean
  lastEvent: WebSocketEvent | null
  subscribe: (eventType: string, handler: EventHandler) => () => void
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null)

interface WebSocketProviderProps {
  children: ReactNode
}

export function WebSocketProvider({ children }: WebSocketProviderProps) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const mountedRef = useRef(true)
  const subscribersRef = useRef<Map<string, Set<EventHandler>>>(new Map())
  const queryClient = useQueryClient()

  // Subscribe to specific event type
  const subscribe = useCallback((eventType: string, handler: EventHandler) => {
    if (!subscribersRef.current.has(eventType)) {
      subscribersRef.current.set(eventType, new Set())
    }
    subscribersRef.current.get(eventType)!.add(handler)

    // Return unsubscribe function
    return () => {
      const handlers = subscribersRef.current.get(eventType)
      if (handlers) {
        handlers.delete(handler)
        if (handlers.size === 0) {
          subscribersRef.current.delete(eventType)
        }
      }
    }
  }, [])

  // Dispatch event to subscribers
  const dispatchEvent = useCallback((event: WebSocketEvent) => {
    const handlers = subscribersRef.current.get(event.event)
    if (handlers) {
      handlers.forEach(handler => handler(event.data))
    }

    // Also dispatch to wildcard subscribers
    const wildcardHandlers = subscribersRef.current.get('*')
    if (wildcardHandlers) {
      wildcardHandlers.forEach(handler => handler(event.data))
    }
  }, [])

  // Handle React Query cache invalidation for specific events
  const handleQueryInvalidation = useCallback((event: WebSocketEvent) => {
    switch (event.event) {
      case 'status.updated':
        queryClient.invalidateQueries({ queryKey: ['status'] })
        break
      case 'backlog.updated':
        queryClient.invalidateQueries({ queryKey: ['backlog'] })
        break
      case 'cost.update':
        queryClient.invalidateQueries({ queryKey: ['costs'] })
        break
      case 'session.started':
      case 'session.ended':
        queryClient.invalidateQueries({ queryKey: ['status'] })
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        queryClient.invalidateQueries({ queryKey: ['timeline'] })
        break
      case 'feature.updated':
        queryClient.invalidateQueries({ queryKey: ['backlog'] })
        queryClient.invalidateQueries({ queryKey: ['timeline'] })
        break
      case 'alert.created':
        queryClient.invalidateQueries({ queryKey: ['alerts'] })
        break
    }
  }, [queryClient])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return

    try {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close()
          return
        }
        setIsConnected(true)
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setIsConnected(false)
        wsRef.current = null

        // Attempt to reconnect
        if (mountedRef.current) {
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect()
          }, 3000)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent
          setLastEvent(data)
          dispatchEvent(data)
          handleQueryInvalidation(data)
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
        }, 3000)
      }
    }
  }, [dispatchEvent, handleQueryInvalidation])

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

  const ping = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    // Set up ping interval
    const pingInterval = setInterval(ping, 30000)

    return () => {
      mountedRef.current = false
      clearInterval(pingInterval)
      disconnect()
    }
  }, [connect, disconnect, ping])

  return (
    <WebSocketContext.Provider value={{ isConnected, lastEvent, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocketContext() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider')
  }
  return context
}

/**
 * Subscribe to a specific WebSocket event type
 */
export function useWebSocketEvent(
  eventType: string,
  handler: EventHandler,
  deps: React.DependencyList = []
) {
  const { subscribe } = useWebSocketContext()
  const handlerRef = useRef(handler)

  useEffect(() => {
    handlerRef.current = handler
  })

  useEffect(() => {
    return subscribe(eventType, (data) => handlerRef.current(data))
  }, [eventType, subscribe, ...deps]) // eslint-disable-line react-hooks/exhaustive-deps
}

export default WebSocketContext
