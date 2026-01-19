import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'
type ResolvedTheme = 'light' | 'dark'

interface ThemeContextValue {
  mode: ThemeMode
  resolvedTheme: ResolvedTheme
  setMode: (mode: ThemeMode) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'ada-theme'

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored
  }
  return 'system'
}

function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode === 'system') {
    return getSystemTheme()
  }
  return mode
}

interface ThemeProviderProps {
  children: ReactNode
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [mode, setModeState] = useState<ThemeMode>(() => getStoredTheme())
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolveTheme(mode))
  const [mounted, setMounted] = useState(false)

  // Apply theme to document
  const applyTheme = useCallback((theme: ResolvedTheme, enableTransitions: boolean) => {
    const root = document.documentElement

    if (enableTransitions) {
      root.classList.add('theme-transition')
    }

    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }

    // Remove transition class after animation completes
    if (enableTransitions) {
      const timeout = setTimeout(() => {
        root.classList.remove('theme-transition')
      }, 300)
      return () => clearTimeout(timeout)
    }
  }, [])

  // Set mode and persist to localStorage
  const setMode = useCallback((newMode: ThemeMode) => {
    setModeState(newMode)
    localStorage.setItem(STORAGE_KEY, newMode)
    const resolved = resolveTheme(newMode)
    setResolvedTheme(resolved)
    applyTheme(resolved, true)
  }, [applyTheme])

  // Initial theme application (without transition to prevent flash)
  useEffect(() => {
    const resolved = resolveTheme(mode)
    setResolvedTheme(resolved)
    applyTheme(resolved, false)
    setMounted(true)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for system theme changes
  useEffect(() => {
    if (mode !== 'system') return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const handleChange = (e: MediaQueryListEvent) => {
      const newTheme = e.matches ? 'dark' : 'light'
      setResolvedTheme(newTheme)
      applyTheme(newTheme, true)
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [mode, applyTheme])

  // Prevent flash of wrong theme on initial render
  if (!mounted) {
    return null
  }

  return (
    <ThemeContext.Provider value={{ mode, resolvedTheme, setMode }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

export default ThemeContext
