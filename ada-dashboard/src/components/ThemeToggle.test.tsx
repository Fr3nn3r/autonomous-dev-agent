import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeToggle } from './ThemeToggle'
import { ThemeProvider } from '../contexts/ThemeContext'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    clear: vi.fn(() => {
      store = {}
    }),
  }
})()

// Mock matchMedia
const createMatchMedia = (matches: boolean) => {
  return vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

function renderWithTheme(component: React.ReactNode) {
  return render(
    <ThemeProvider>
      {component}
    </ThemeProvider>
  )
}

describe('ThemeToggle', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', { value: localStorageMock })
    localStorageMock.clear()
    document.documentElement.classList.remove('dark')
    window.matchMedia = createMatchMedia(true)
  })

  it('should render three theme buttons', () => {
    renderWithTheme(<ThemeToggle />)

    expect(screen.getByRole('radio', { name: 'Light' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'System' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument()
  })

  it('should have system mode selected by default', () => {
    renderWithTheme(<ThemeToggle />)

    expect(screen.getByRole('radio', { name: 'System' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'false')
  })

  it('should switch to light mode when light button clicked', () => {
    renderWithTheme(<ThemeToggle />)

    fireEvent.click(screen.getByRole('radio', { name: 'Light' }))

    expect(screen.getByRole('radio', { name: 'Light' })).toHaveAttribute('aria-checked', 'true')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('ada-theme', 'light')
  })

  it('should switch to dark mode when dark button clicked', () => {
    renderWithTheme(<ThemeToggle />)

    fireEvent.click(screen.getByRole('radio', { name: 'Dark' }))

    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('ada-theme', 'dark')
  })

  it('should apply custom className', () => {
    renderWithTheme(<ThemeToggle className="custom-class" />)

    const container = screen.getByRole('radiogroup')
    expect(container).toHaveClass('custom-class')
  })

  it('should have proper radiogroup role for accessibility', () => {
    renderWithTheme(<ThemeToggle />)

    expect(screen.getByRole('radiogroup', { name: 'Theme selection' })).toBeInTheDocument()
  })

  it('should display correct visual state for active button', () => {
    localStorageMock.getItem.mockReturnValueOnce('dark')

    renderWithTheme(<ThemeToggle />)

    const darkButton = screen.getByRole('radio', { name: 'Dark' })
    expect(darkButton).toHaveAttribute('aria-checked', 'true')
  })
})
