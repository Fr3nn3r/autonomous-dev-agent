import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useWebSocket } from './websocket'

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((error: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose()
    }
  })

  // Helper to simulate connection open
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    if (this.onopen) {
      this.onopen()
    }
  }

  // Helper to simulate message received
  simulateMessage(data: object) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent)
    }
  }

  // Helper to simulate connection close
  simulateClose() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose()
    }
  }
}

// Replace global WebSocket
const originalWebSocket = global.WebSocket
beforeEach(() => {
  MockWebSocket.instances = []
  // @ts-expect-error - Mocking WebSocket
  global.WebSocket = MockWebSocket
  vi.useFakeTimers()
})

afterEach(() => {
  global.WebSocket = originalWebSocket
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useWebSocket', () => {
  it('should create only one WebSocket connection on mount', () => {
    const { unmount } = renderHook(() => useWebSocket())

    // Should have created exactly one WebSocket instance
    expect(MockWebSocket.instances.length).toBe(1)

    unmount()
  })

  it('should not create new connections when callbacks change', async () => {
    let onConnectCount = 0
    let renderCount = 0

    const { rerender } = renderHook(
      ({ onConnect }) => {
        renderCount++
        return useWebSocket({ onConnect })
      },
      {
        initialProps: {
          onConnect: () => {
            onConnectCount++
          },
        },
      }
    )

    // Simulate connection open
    MockWebSocket.instances[0].simulateOpen()

    expect(onConnectCount).toBe(1)
    expect(MockWebSocket.instances.length).toBe(1)

    // Rerender with a new callback function (simulates what happens when parent re-renders)
    rerender({
      onConnect: () => {
        onConnectCount++
      },
    })

    // Should still have only one WebSocket instance
    expect(MockWebSocket.instances.length).toBe(1)

    // Rerender multiple times
    for (let i = 0; i < 5; i++) {
      rerender({
        onConnect: () => {
          onConnectCount++
        },
      })
    }

    // Should still have only one WebSocket instance (no reconnection loops)
    expect(MockWebSocket.instances.length).toBe(1)
  })

  it('should close connection on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    expect(ws.readyState).toBe(MockWebSocket.OPEN)

    unmount()

    expect(ws.close).toHaveBeenCalled()
  })

  it('should not reconnect after unmount', () => {
    const { unmount } = renderHook(() =>
      useWebSocket({ reconnectInterval: 1000 })
    )

    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    // Unmount the component
    unmount()

    // Simulate the connection closing
    ws.simulateClose()

    // Advance timers past reconnect interval
    act(() => {
      vi.advanceTimersByTime(2000)
    })

    // Should not have created a new WebSocket
    expect(MockWebSocket.instances.length).toBe(1)
  })

  it('should prevent duplicate connections when already connecting', () => {
    const { result } = renderHook(() => useWebSocket())

    // First connection attempt (from mount) - still in CONNECTING state
    expect(MockWebSocket.instances.length).toBe(1)
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CONNECTING)

    // Manually call reconnect - should not create new connection
    act(() => {
      result.current.reconnect()
    })

    // Should still have only one WebSocket instance
    expect(MockWebSocket.instances.length).toBe(1)
  })

  it('should prevent duplicate connections when already open', () => {
    const { result } = renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]
    ws.simulateOpen()

    expect(MockWebSocket.instances.length).toBe(1)
    expect(ws.readyState).toBe(MockWebSocket.OPEN)

    // Manually call reconnect - should not create new connection
    act(() => {
      result.current.reconnect()
    })

    // Should still have only one WebSocket instance
    expect(MockWebSocket.instances.length).toBe(1)
  })

  it('should update isConnected state correctly', async () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.isConnected).toBe(false)

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    expect(result.current.isConnected).toBe(true)

    act(() => {
      ws.simulateClose()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('should call onConnect callback when connection opens', () => {
    const onConnect = vi.fn()
    renderHook(() => useWebSocket({ onConnect }))

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    expect(onConnect).toHaveBeenCalledTimes(1)
  })

  it('should call onDisconnect callback when connection closes', () => {
    const onDisconnect = vi.fn()
    renderHook(() => useWebSocket({ onDisconnect }))

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      ws.simulateClose()
    })

    expect(onDisconnect).toHaveBeenCalledTimes(1)
  })

  it('should call onEvent callback when message received', () => {
    const onEvent = vi.fn()
    renderHook(() => useWebSocket({ onEvent }))

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    const eventData = {
      event: 'test.event',
      data: { foo: 'bar' },
      timestamp: new Date().toISOString(),
    }

    act(() => {
      ws.simulateMessage(eventData)
    })

    expect(onEvent).toHaveBeenCalledWith(eventData)
  })

  it('should update lastEvent when message received', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.lastEvent).toBeNull()

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    const eventData = {
      event: 'test.event',
      data: { foo: 'bar' },
      timestamp: new Date().toISOString(),
    }

    act(() => {
      ws.simulateMessage(eventData)
    })

    expect(result.current.lastEvent).toEqual(eventData)
  })

  it('should attempt to reconnect after connection loss', () => {
    renderHook(() => useWebSocket({ reconnectInterval: 1000 }))

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      ws.simulateClose()
    })

    expect(MockWebSocket.instances.length).toBe(1)

    // Advance timers past reconnect interval
    act(() => {
      vi.advanceTimersByTime(1500)
    })

    // Should have created a new WebSocket for reconnection
    expect(MockWebSocket.instances.length).toBe(2)
  })

  it('should send ping messages', () => {
    const { result } = renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      result.current.ping()
    })

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
  })

  it('should not send messages when not connected', () => {
    const { result } = renderHook(() => useWebSocket())

    const ws = MockWebSocket.instances[0]
    // Don't simulate open - stay in CONNECTING state

    act(() => {
      result.current.sendMessage('test', { data: 'value' })
    })

    expect(ws.send).not.toHaveBeenCalled()
  })

  it('should clear reconnect timeout on unmount', () => {
    const { unmount } = renderHook(() =>
      useWebSocket({ reconnectInterval: 1000 })
    )

    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      ws.simulateClose()
    })

    // Unmount before reconnect timeout fires
    unmount()

    // Advance timers
    act(() => {
      vi.advanceTimersByTime(2000)
    })

    // Should not have attempted to reconnect
    expect(MockWebSocket.instances.length).toBe(1)
  })

  it('should handle rapid connect/disconnect cycles without errors', () => {
    const onConnect = vi.fn()
    const onDisconnect = vi.fn()

    const { unmount } = renderHook(() =>
      useWebSocket({ onConnect, onDisconnect, reconnectInterval: 100 })
    )

    const ws = MockWebSocket.instances[0]

    // Rapidly open and close
    for (let i = 0; i < 5; i++) {
      act(() => {
        ws.readyState = MockWebSocket.OPEN
        if (ws.onopen) ws.onopen()
      })

      act(() => {
        ws.readyState = MockWebSocket.CLOSED
        if (ws.onclose) ws.onclose()
      })
    }

    // Should not throw errors
    unmount()
  })
})
