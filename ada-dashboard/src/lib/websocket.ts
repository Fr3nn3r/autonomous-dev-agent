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
    onConnect,
    onDisconnect,
    onEvent,
    reconnectInterval = 3000,
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setIsConnected(true)
        onConnect?.()
      }

      ws.onclose = () => {
        setIsConnected(false)
        onDisconnect?.()

        // Attempt to reconnect
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect()
        }, reconnectInterval)
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent
          setLastEvent(data)
          onEvent?.(data)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to connect WebSocket:', error)

      // Attempt to reconnect
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, reconnectInterval)
    }
  }, [onConnect, onDisconnect, onEvent, reconnectInterval])

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
    connect()

    // Set up ping interval to keep connection alive
    const pingInterval = setInterval(ping, 30000)

    return () => {
      clearInterval(pingInterval)
      disconnect()
    }
  }, [connect, disconnect, ping])

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
 * Subscribe to specific event types
 */
export function useWebSocketEvent(
  eventType: string,
  callback: (data: Record<string, unknown>) => void
) {
  const { lastEvent } = useWebSocket()

  useEffect(() => {
    if (lastEvent?.event === eventType) {
      callback(lastEvent.data)
    }
  }, [lastEvent, eventType, callback])
}

export default useWebSocket
