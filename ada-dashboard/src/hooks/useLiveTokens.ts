import { useState, useCallback, useRef, useEffect } from 'react'
import { useWebSocketEvent } from '../contexts/WebSocketContext'

interface TokenCounts {
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  totalCostUsd: number
}

interface UseLiveTokensReturn extends TokenCounts {
  isAnimating: boolean
  lastUpdate: Date | null
}

/**
 * Hook for live token counting with animation support.
 * Subscribes to cost.update WebSocket events and provides animated counters.
 */
export function useLiveTokens(initialValues?: Partial<TokenCounts>): UseLiveTokensReturn {
  const [tokens, setTokens] = useState<TokenCounts>({
    inputTokens: initialValues?.inputTokens ?? 0,
    outputTokens: initialValues?.outputTokens ?? 0,
    cacheReadTokens: initialValues?.cacheReadTokens ?? 0,
    cacheWriteTokens: initialValues?.cacheWriteTokens ?? 0,
    totalCostUsd: initialValues?.totalCostUsd ?? 0,
  })

  const [isAnimating, setIsAnimating] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const animationTimeoutRef = useRef<number | null>(null)

  // Clean up animation timeout
  useEffect(() => {
    return () => {
      if (animationTimeoutRef.current) {
        clearTimeout(animationTimeoutRef.current)
      }
    }
  }, [])

  const handleCostUpdate = useCallback((data: Record<string, unknown>) => {
    // Extract token counts from the event data
    const newTokens: Partial<TokenCounts> = {}

    if (typeof data.input_tokens === 'number') {
      newTokens.inputTokens = data.input_tokens
    }
    if (typeof data.output_tokens === 'number') {
      newTokens.outputTokens = data.output_tokens
    }
    if (typeof data.cache_read_tokens === 'number') {
      newTokens.cacheReadTokens = data.cache_read_tokens
    }
    if (typeof data.cache_write_tokens === 'number') {
      newTokens.cacheWriteTokens = data.cache_write_tokens
    }
    if (typeof data.total_cost_usd === 'number') {
      newTokens.totalCostUsd = data.total_cost_usd
    }

    // Update state if any new values
    if (Object.keys(newTokens).length > 0) {
      setTokens(prev => ({
        ...prev,
        ...newTokens,
      }))

      // Trigger animation
      setIsAnimating(true)
      setLastUpdate(new Date())

      // Clear any existing animation timeout
      if (animationTimeoutRef.current) {
        clearTimeout(animationTimeoutRef.current)
      }

      // Reset animation state after animation completes
      animationTimeoutRef.current = window.setTimeout(() => {
        setIsAnimating(false)
      }, 300)
    }
  }, [])

  useWebSocketEvent('cost.update', handleCostUpdate)

  return {
    ...tokens,
    isAnimating,
    lastUpdate,
  }
}

/**
 * Hook for animating a number incrementing from one value to another.
 * Useful for creating smooth counter animations.
 */
export function useAnimatedCounter(
  targetValue: number,
  duration: number = 300
): { displayValue: number; isAnimating: boolean } {
  const [displayValue, setDisplayValue] = useState(targetValue)
  const [isAnimating, setIsAnimating] = useState(false)
  const previousValueRef = useRef(targetValue)
  const animationFrameRef = useRef<number | null>(null)
  const startTimeRef = useRef<number | null>(null)

  useEffect(() => {
    const previousValue = previousValueRef.current

    if (previousValue === targetValue) {
      return
    }

    const animate = (currentTime: number) => {
      if (startTimeRef.current === null) {
        startTimeRef.current = currentTime
        setIsAnimating(true)
      }

      const elapsed = currentTime - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)

      // Ease-out cubic
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      const currentValue = previousValue + (targetValue - previousValue) * easedProgress

      setDisplayValue(Math.round(currentValue))

      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animate)
      } else {
        setDisplayValue(targetValue)
        setIsAnimating(false)
        startTimeRef.current = null
        previousValueRef.current = targetValue
      }
    }

    animationFrameRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [targetValue, duration])

  return { displayValue, isAnimating }
}

export default useLiveTokens
