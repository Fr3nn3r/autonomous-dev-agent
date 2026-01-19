import { useAnimatedCounter } from '../hooks/useLiveTokens'

interface LiveTokenCounterProps {
  value: number
  label: string
  format?: 'number' | 'currency' | 'tokens'
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

function formatNumber(value: number, format: 'number' | 'currency' | 'tokens'): string {
  switch (format) {
    case 'currency':
      return `$${value.toFixed(4)}`
    case 'tokens':
      if (value < 1000) return String(value)
      if (value < 1_000_000) return `${(value / 1000).toFixed(1)}K`
      return `${(value / 1_000_000).toFixed(2)}M`
    default:
      return value.toLocaleString()
  }
}

export function LiveTokenCounter({
  value,
  label,
  format = 'tokens',
  className = '',
  size = 'md',
}: LiveTokenCounterProps) {
  const { displayValue, isAnimating } = useAnimatedCounter(value)

  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-lg',
    lg: 'text-2xl',
  }

  return (
    <div className={`${className}`}>
      <p className="text-gray-500 dark:text-gray-400 text-sm">{label}</p>
      <p
        className={`font-semibold ${sizeClasses[size]} ${
          isAnimating ? 'token-counter-animate' : ''
        }`}
      >
        {formatNumber(displayValue, format)}
      </p>
    </div>
  )
}

interface TokenCounterGroupProps {
  inputTokens: number
  outputTokens: number
  totalCostUsd?: number
  className?: string
}

export function TokenCounterGroup({
  inputTokens,
  outputTokens,
  totalCostUsd,
  className = '',
}: TokenCounterGroupProps) {
  return (
    <div className={`grid grid-cols-2 gap-4 ${className}`}>
      <div className="bg-gray-100 dark:bg-gray-700/50 rounded p-3">
        <LiveTokenCounter value={inputTokens} label="Input Tokens" format="tokens" />
      </div>
      <div className="bg-gray-100 dark:bg-gray-700/50 rounded p-3">
        <LiveTokenCounter value={outputTokens} label="Output Tokens" format="tokens" />
      </div>
      {totalCostUsd !== undefined && (
        <div className="bg-gray-100 dark:bg-gray-700/50 rounded p-3 col-span-2">
          <LiveTokenCounter value={totalCostUsd} label="Total Cost" format="currency" size="lg" />
        </div>
      )}
    </div>
  )
}

export default LiveTokenCounter
