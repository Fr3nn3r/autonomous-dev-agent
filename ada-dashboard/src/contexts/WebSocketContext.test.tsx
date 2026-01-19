import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WebSocketProvider, useWebSocketContext, useWebSocketEvent } from './WebSocketContext'

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

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    if (this.onopen) {
      this.onopen()
    }
  }

  simulateMessage(data: object) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent)
    }
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose()
    }
  }
}

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          {children}
        </WebSocketProvider>
      </QueryClientProvider>
    )
  }
}

// Test component
function TestConsumer() {
  const { isConnected, lastEvent } = useWebSocketContext()
  return (
    <div>
      <span data-testid="connected">{isConnected ? 'yes' : 'no'}</span>
      <span data-testid="last-event">{lastEvent?.event || 'none'}</span>
    </div>
  )
}

const originalWebSocket = global.WebSocket

describe('WebSocketContext', () => {
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

  it('should provide connection status', () => {
    const Wrapper = createWrapper()

    render(
      <Wrapper>
        <TestConsumer />
      </Wrapper>
    )

    expect(screen.getByTestId('connected')).toHaveTextContent('no')

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    expect(screen.getByTestId('connected')).toHaveTextContent('yes')
  })

  it('should provide last event', () => {
    const Wrapper = createWrapper()

    render(
      <Wrapper>
        <TestConsumer />
      </Wrapper>
    )

    expect(screen.getByTestId('last-event')).toHaveTextContent('none')

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    act(() => {
      MockWebSocket.instances[0].simulateMessage({
        event: 'test.event',
        data: { foo: 'bar' },
        timestamp: new Date().toISOString(),
      })
    })

    expect(screen.getByTestId('last-event')).toHaveTextContent('test.event')
  })

  it('should throw error when used outside provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<TestConsumer />)
    }).toThrow('useWebSocketContext must be used within a WebSocketProvider')

    consoleSpy.mockRestore()
  })

  describe('useWebSocketEvent', () => {
    it('should call handler when matching event received', () => {
      const handler = vi.fn()
      const Wrapper = createWrapper()

      function EventConsumer() {
        useWebSocketEvent('test.event', handler)
        return null
      }

      render(
        <Wrapper>
          <EventConsumer />
        </Wrapper>
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      act(() => {
        MockWebSocket.instances[0].simulateMessage({
          event: 'test.event',
          data: { foo: 'bar' },
          timestamp: new Date().toISOString(),
        })
      })

      expect(handler).toHaveBeenCalledWith({ foo: 'bar' })
    })

    it('should not call handler for non-matching events', () => {
      const handler = vi.fn()
      const Wrapper = createWrapper()

      function EventConsumer() {
        useWebSocketEvent('test.event', handler)
        return null
      }

      render(
        <Wrapper>
          <EventConsumer />
        </Wrapper>
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      act(() => {
        MockWebSocket.instances[0].simulateMessage({
          event: 'other.event',
          data: { foo: 'bar' },
          timestamp: new Date().toISOString(),
        })
      })

      expect(handler).not.toHaveBeenCalled()
    })
  })

  describe('subscribe', () => {
    it('should allow subscribing to events', () => {
      const handler = vi.fn()
      const Wrapper = createWrapper()

      function SubscribeConsumer() {
        const { subscribe } = useWebSocketContext()

        // Subscribe on mount
        React.useEffect(() => {
          const unsubscribe = subscribe('custom.event', handler)
          return unsubscribe
        }, [subscribe])

        return null
      }

      // Need to import React for useEffect
      const React = require('react')

      render(
        <Wrapper>
          <SubscribeConsumer />
        </Wrapper>
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      act(() => {
        MockWebSocket.instances[0].simulateMessage({
          event: 'custom.event',
          data: { value: 123 },
          timestamp: new Date().toISOString(),
        })
      })

      expect(handler).toHaveBeenCalledWith({ value: 123 })
    })

    it('should unsubscribe when returned function is called', () => {
      const handler = vi.fn()
      let unsubscribeFn: (() => void) | null = null
      const Wrapper = createWrapper()

      function SubscribeConsumer() {
        const { subscribe } = useWebSocketContext()

        React.useEffect(() => {
          unsubscribeFn = subscribe('custom.event', handler)
        }, [subscribe])

        return null
      }

      const React = require('react')

      render(
        <Wrapper>
          <SubscribeConsumer />
        </Wrapper>
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      // Unsubscribe
      act(() => {
        unsubscribeFn?.()
      })

      act(() => {
        MockWebSocket.instances[0].simulateMessage({
          event: 'custom.event',
          data: { value: 123 },
          timestamp: new Date().toISOString(),
        })
      })

      expect(handler).not.toHaveBeenCalled()
    })
  })
})
