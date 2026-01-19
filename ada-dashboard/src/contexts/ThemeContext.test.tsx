import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ThemeProvider, useTheme, type ThemeMode } from './ThemeContext'

// Test component to access theme context
function ThemeConsumer() {
  const { mode, resolvedTheme, setMode } = useTheme()
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setMode('light')}>Light</button>
      <button onClick={() => setMode('dark')}>Dark</button>
      <button onClick={() => setMode('system')}>System</button>
    </div>
  )
}

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()

// Mock matchMedia
const createMatchMedia = (matches: boolean) => {
  const listeners: ((e: MediaQueryListEvent) => void)[] = []
  return vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn((event: string, listener: (e: MediaQueryListEvent) => void) => {
      listeners.push(listener)
    }),
    removeEventListener: vi.fn((event: string, listener: (e: MediaQueryListEvent) => void) => {
      const index = listeners.indexOf(listener)
      if (index > -1) listeners.splice(index, 1)
    }),
    dispatchEvent: vi.fn(),
    // Helper to trigger change
    _triggerChange: (newMatches: boolean) => {
      listeners.forEach(listener => listener({ matches: newMatches } as MediaQueryListEvent))
    },
  }))
}

describe('ThemeContext', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', { value: localStorageMock })
    localStorageMock.clear()
    document.documentElement.classList.remove('dark')
    document.documentElement.classList.remove('theme-transition')
    window.matchMedia = createMatchMedia(true) // Default to dark system preference
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should provide default system mode when no stored preference', () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('system')
  })

  it('should load stored theme preference from localStorage', () => {
    localStorageMock.getItem.mockReturnValueOnce('dark')

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('dark')
  })

  it('should resolve system theme based on prefers-color-scheme', () => {
    window.matchMedia = createMatchMedia(true) // Dark mode preference

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('system')
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark')
  })

  it('should resolve to light when system prefers light', () => {
    window.matchMedia = createMatchMedia(false) // Light mode preference

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('resolved')).toHaveTextContent('light')
  })

  it('should change theme mode when setMode is called', () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    fireEvent.click(screen.getByText('Light'))
    expect(screen.getByTestId('mode')).toHaveTextContent('light')
    expect(screen.getByTestId('resolved')).toHaveTextContent('light')

    fireEvent.click(screen.getByText('Dark'))
    expect(screen.getByTestId('mode')).toHaveTextContent('dark')
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark')
  })

  it('should persist theme preference to localStorage', () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    fireEvent.click(screen.getByText('Dark'))
    expect(localStorageMock.setItem).toHaveBeenCalledWith('ada-theme', 'dark')
  })

  it('should apply dark class to document when theme is dark', () => {
    localStorageMock.getItem.mockReturnValueOnce('dark')

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('should remove dark class when theme is light', () => {
    document.documentElement.classList.add('dark')
    localStorageMock.getItem.mockReturnValueOnce('light')

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('should throw error when useTheme is used outside provider', () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<ThemeConsumer />)
    }).toThrow('useTheme must be used within a ThemeProvider')

    consoleSpy.mockRestore()
  })

  it('should handle invalid stored theme value', () => {
    localStorageMock.getItem.mockReturnValueOnce('invalid')

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    // Should default to system
    expect(screen.getByTestId('mode')).toHaveTextContent('system')
  })
})
