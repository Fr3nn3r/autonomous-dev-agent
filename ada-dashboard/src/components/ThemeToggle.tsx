import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme, type ThemeMode } from '../contexts/ThemeContext'

interface ThemeToggleProps {
  className?: string
}

export function ThemeToggle({ className = '' }: ThemeToggleProps) {
  const { mode, setMode } = useTheme()

  const modes: { value: ThemeMode; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'system', icon: Monitor, label: 'System' },
    { value: 'dark', icon: Moon, label: 'Dark' },
  ]

  return (
    <div
      className={`inline-flex items-center gap-1 p-1 rounded-lg bg-gray-200 dark:bg-gray-700 ${className}`}
      role="radiogroup"
      aria-label="Theme selection"
    >
      {modes.map(({ value, icon: Icon, label }) => {
        const isActive = mode === value
        return (
          <button
            key={value}
            onClick={() => setMode(value)}
            className={`
              p-2 rounded-md transition-all duration-200
              ${isActive
                ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }
            `}
            role="radio"
            aria-checked={isActive}
            aria-label={label}
            title={label}
          >
            <Icon className="w-4 h-4" />
          </button>
        )
      })}
    </div>
  )
}

export default ThemeToggle
