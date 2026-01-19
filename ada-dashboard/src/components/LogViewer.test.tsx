import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LogViewer } from './LogViewer'

// Mock the WebSocketContext
vi.mock('../contexts/WebSocketContext', () => ({
  useWebSocketEvent: vi.fn(),
}))

// Mock the api-client
vi.mock('../lib/api-client', () => ({
  apiClient: {
    getProgress: vi.fn().mockResolvedValue({
      content: 'Initial log line 1\nInitial log line 2\nInitial log line 3',
      lines: 3,
      total_lines: 3,
      file_size_kb: 0.1,
    }),
  },
}))

function renderWithQuery(component: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      {component}
    </QueryClientProvider>
  )
}

describe('LogViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render header with Live Logs title', async () => {
    renderWithQuery(<LogViewer />)

    expect(screen.getByText('Live Logs')).toBeInTheDocument()
  })

  it('should show pause/play button', () => {
    renderWithQuery(<LogViewer />)

    // Should have pause button initially (icon has title="Pause auto-update")
    expect(screen.getByTitle('Pause auto-update')).toBeInTheDocument()
  })

  it('should toggle pause state when pause button clicked', async () => {
    renderWithQuery(<LogViewer />)

    const pauseButton = screen.getByTitle('Pause auto-update')
    fireEvent.click(pauseButton)

    // Should now show play button
    expect(screen.getByTitle('Resume auto-update')).toBeInTheDocument()
  })

  it('should show filter input when showFilter is true', () => {
    renderWithQuery(<LogViewer showFilter={true} />)

    expect(screen.getByPlaceholderText('Filter logs...')).toBeInTheDocument()
  })

  it('should hide filter input when showFilter is false', () => {
    renderWithQuery(<LogViewer showFilter={false} />)

    expect(screen.queryByPlaceholderText('Filter logs...')).not.toBeInTheDocument()
  })

  it('should filter logs based on input', async () => {
    const { apiClient } = await import('../lib/api-client')
    vi.mocked(apiClient.getProgress).mockResolvedValueOnce({
      content: 'Error: something failed\nInfo: all good\nWarning: be careful',
      lines: 3,
      total_lines: 3,
      file_size_kb: 0.1,
    })

    renderWithQuery(<LogViewer showFilter={true} />)

    // Wait for logs to load
    await waitFor(() => {
      expect(screen.getByText(/Error: something failed/)).toBeInTheDocument()
    })

    // Enter filter text
    const filterInput = screen.getByPlaceholderText('Filter logs...')
    fireEvent.change(filterInput, { target: { value: 'Error' } })

    // Should only show matching line
    expect(screen.getByText(/Error: something failed/)).toBeInTheDocument()
    expect(screen.queryByText(/Info: all good/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Warning: be careful/)).not.toBeInTheDocument()
  })

  it('should show empty state when no logs', async () => {
    const { apiClient } = await import('../lib/api-client')
    vi.mocked(apiClient.getProgress).mockResolvedValueOnce({
      content: '',
      lines: 0,
      total_lines: 0,
      file_size_kb: 0,
    })

    renderWithQuery(<LogViewer />)

    await waitFor(() => {
      expect(screen.getByText('No log entries yet')).toBeInTheDocument()
    })
  })

  it('should apply custom className', () => {
    const { container } = renderWithQuery(<LogViewer className="custom-class" />)

    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('should show line count in footer', async () => {
    const { apiClient } = await import('../lib/api-client')
    vi.mocked(apiClient.getProgress).mockResolvedValueOnce({
      content: 'Line 1\nLine 2\nLine 3',
      lines: 3,
      total_lines: 3,
      file_size_kb: 0.1,
    })

    renderWithQuery(<LogViewer />)

    await waitFor(() => {
      expect(screen.getByText(/3 \/ 3 lines/)).toBeInTheDocument()
    })
  })

  it('should show filtered text when filter is active', async () => {
    const { apiClient } = await import('../lib/api-client')
    vi.mocked(apiClient.getProgress).mockResolvedValueOnce({
      content: 'Line 1\nLine 2\nLine 3',
      lines: 3,
      total_lines: 3,
      file_size_kb: 0.1,
    })

    renderWithQuery(<LogViewer showFilter={true} />)

    await waitFor(() => {
      expect(screen.getByText('Line 1')).toBeInTheDocument()
    })

    const filterInput = screen.getByPlaceholderText('Filter logs...')
    fireEvent.change(filterInput, { target: { value: '1' } })

    expect(screen.getByText(/\(filtered\)/)).toBeInTheDocument()
  })

  it('should show paused indicator when paused', () => {
    renderWithQuery(<LogViewer />)

    const pauseButton = screen.getByTitle('Pause auto-update')
    fireEvent.click(pauseButton)

    expect(screen.getByText('Paused -')).toBeInTheDocument()
  })

  it('should handle timestamps visibility', async () => {
    const { apiClient } = await import('../lib/api-client')
    vi.mocked(apiClient.getProgress).mockResolvedValueOnce({
      content: 'Test log line',
      lines: 1,
      total_lines: 1,
      file_size_kb: 0.1,
    })

    renderWithQuery(<LogViewer showTimestamps={true} />)

    await waitFor(() => {
      expect(screen.getByText('Test log line')).toBeInTheDocument()
    })

    // When timestamps are shown, there should be a time displayed
    // The time format varies by locale, but there should be a colon
    const container = screen.getByText('Test log line').parentElement
    expect(container?.textContent).toMatch(/\d+:\d+/)
  })
})
