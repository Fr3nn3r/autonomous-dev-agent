import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAnimatedCounter } from './useLiveTokens'

// Mock requestAnimationFrame
let rafCallbacks: ((time: number) => void)[] = []
let rafTime = 0

const mockRequestAnimationFrame = vi.fn((callback: (time: number) => void) => {
  rafCallbacks.push(callback)
  return rafCallbacks.length
})

const mockCancelAnimationFrame = vi.fn((id: number) => {
  rafCallbacks = rafCallbacks.filter((_, index) => index + 1 !== id)
})

// Helper to flush raf callbacks
function flushRafCallbacks(advanceTime: number = 16) {
  rafTime += advanceTime
  const callbacks = [...rafCallbacks]
  rafCallbacks = []
  callbacks.forEach(callback => callback(rafTime))
}

describe('useAnimatedCounter', () => {
  beforeEach(() => {
    rafCallbacks = []
    rafTime = 0
    vi.stubGlobal('requestAnimationFrame', mockRequestAnimationFrame)
    vi.stubGlobal('cancelAnimationFrame', mockCancelAnimationFrame)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('should start with the initial value', () => {
    const { result } = renderHook(() => useAnimatedCounter(100))

    expect(result.current.displayValue).toBe(100)
    expect(result.current.isAnimating).toBe(false)
  })

  it('should animate to new value', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 0 } }
    )

    expect(result.current.displayValue).toBe(0)

    rerender({ value: 100 })

    // Flush initial raf callback
    act(() => {
      flushRafCallbacks(0) // First frame sets start time
    })

    // Should start animating
    expect(result.current.isAnimating).toBe(true)

    // Advance through animation
    for (let i = 0; i < 20; i++) {
      act(() => {
        flushRafCallbacks(20) // 20ms per frame
      })
    }

    // After 400ms, animation should be complete
    expect(result.current.displayValue).toBe(100)
    expect(result.current.isAnimating).toBe(false)
  })

  it('should handle decreasing values', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 100 } }
    )

    expect(result.current.displayValue).toBe(100)

    rerender({ value: 50 })

    // Flush through animation
    for (let i = 0; i < 25; i++) {
      act(() => {
        flushRafCallbacks(20)
      })
    }

    expect(result.current.displayValue).toBe(50)
  })

  it('should not animate when value stays the same', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 100 } }
    )

    expect(result.current.isAnimating).toBe(false)

    rerender({ value: 100 })

    expect(result.current.isAnimating).toBe(false)
    expect(result.current.displayValue).toBe(100)
    expect(mockRequestAnimationFrame).not.toHaveBeenCalled()
  })

  it('should round display value to integer', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 0 } }
    )

    rerender({ value: 100 })

    // Flush a few frames
    for (let i = 0; i < 5; i++) {
      act(() => {
        flushRafCallbacks(20)
      })
    }

    // Should be a whole number at any point
    expect(Number.isInteger(result.current.displayValue)).toBe(true)
  })

  it('should progress through animation', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 0 } }
    )

    rerender({ value: 100 })

    // Flush initial frame
    act(() => {
      flushRafCallbacks(0)
    })

    // After some frames, value should be between 0 and 100
    act(() => {
      flushRafCallbacks(100)
    })

    const midValue = result.current.displayValue
    expect(midValue).toBeGreaterThan(0)
    expect(midValue).toBeLessThan(100)
  })

  it('should handle rapid value changes', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedCounter(value, 300),
      { initialProps: { value: 0 } }
    )

    // Start first animation
    rerender({ value: 100 })

    // Flush a few frames
    for (let i = 0; i < 5; i++) {
      act(() => {
        flushRafCallbacks(20)
      })
    }

    // Change value mid-animation
    rerender({ value: 200 })

    // Complete the new animation
    for (let i = 0; i < 25; i++) {
      act(() => {
        flushRafCallbacks(20)
      })
    }

    // Final value should be 200
    expect(result.current.displayValue).toBe(200)
  })
})
