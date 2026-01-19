import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FeatureCard } from './FeatureCard'
import type { Feature } from '../lib/api-client'

const mockFeature: Feature = {
  id: 'feature-1',
  name: 'Test Feature',
  description: 'A test feature description',
  category: 'core',
  status: 'pending',
  priority: 2,
  sessions_spent: 3,
  depends_on: [],
  acceptance_criteria: ['Criterion 1', 'Criterion 2'],
  implementation_notes: ['Note 1'],
  model_override: null,
}

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

describe('FeatureCard', () => {
  it('should render feature name and description', () => {
    renderWithQuery(<FeatureCard feature={mockFeature} />)

    expect(screen.getByText('Test Feature')).toBeInTheDocument()
    expect(screen.getByText('A test feature description')).toBeInTheDocument()
  })

  it('should show session count', () => {
    renderWithQuery(<FeatureCard feature={mockFeature} />)

    expect(screen.getByText('3 sessions')).toBeInTheDocument()
  })

  it('should show singular session text when 1 session', () => {
    const featureWith1Session = { ...mockFeature, sessions_spent: 1 }
    renderWithQuery(<FeatureCard feature={featureWith1Session} />)

    expect(screen.getByText('1 session')).toBeInTheDocument()
  })

  it('should not show session count when 0 sessions', () => {
    const featureNoSessions = { ...mockFeature, sessions_spent: 0 }
    renderWithQuery(<FeatureCard feature={featureNoSessions} />)

    expect(screen.queryByText(/session/)).not.toBeInTheDocument()
  })

  it('should show priority badge', () => {
    renderWithQuery(<FeatureCard feature={mockFeature} />)

    expect(screen.getByText('P2')).toBeInTheDocument()
  })

  it('should expand when clicked (uncontrolled)', () => {
    renderWithQuery(<FeatureCard feature={mockFeature} />)

    // Should show description in collapsed state
    expect(screen.getByText('A test feature description')).toBeInTheDocument()

    // Click to expand
    fireEvent.click(screen.getByRole('button'))

    // Should show acceptance criteria when expanded
    expect(screen.getByText('Acceptance Criteria')).toBeInTheDocument()
  })

  it('should call onToggle when clicked (controlled)', () => {
    const onToggle = vi.fn()

    renderWithQuery(
      <FeatureCard
        feature={mockFeature}
        isExpanded={false}
        onToggle={onToggle}
      />
    )

    fireEvent.click(screen.getByRole('button'))

    expect(onToggle).toHaveBeenCalledWith('feature-1')
  })

  it('should show expanded content when isExpanded is true', () => {
    renderWithQuery(
      <FeatureCard
        feature={mockFeature}
        isExpanded={true}
        onToggle={() => {}}
      />
    )

    // Should show full details
    expect(screen.getByText('Description')).toBeInTheDocument()
    expect(screen.getByText('Acceptance Criteria')).toBeInTheDocument()
  })

  it('should hide expanded content when isExpanded is false', () => {
    renderWithQuery(
      <FeatureCard
        feature={mockFeature}
        isExpanded={false}
        onToggle={() => {}}
      />
    )

    // Should not show details section header
    expect(screen.queryByText('Acceptance Criteria')).not.toBeInTheDocument()
  })

  describe('status icons', () => {
    it('should show check icon for completed status', () => {
      const completedFeature = { ...mockFeature, status: 'completed' }
      renderWithQuery(<FeatureCard feature={completedFeature} />)

      // Check for green check icon (via the text-green-500 class)
      const statusIcon = document.querySelector('.text-green-500')
      expect(statusIcon).toBeInTheDocument()
    })

    it('should show spinning icon for in_progress status', () => {
      const inProgressFeature = { ...mockFeature, status: 'in_progress' }
      renderWithQuery(<FeatureCard feature={inProgressFeature} />)

      // Check for yellow spinning icon
      const statusIcon = document.querySelector('.text-yellow-500.animate-spin')
      expect(statusIcon).toBeInTheDocument()
    })

    it('should show alert icon for blocked status', () => {
      const blockedFeature = { ...mockFeature, status: 'blocked' }
      renderWithQuery(<FeatureCard feature={blockedFeature} />)

      // Check for red alert icon
      const statusIcon = document.querySelector('.text-red-500')
      expect(statusIcon).toBeInTheDocument()
    })
  })

  describe('priority badge colors', () => {
    it('should show red badge for priority 1', () => {
      const p1Feature = { ...mockFeature, priority: 1 }
      renderWithQuery(<FeatureCard feature={p1Feature} />)

      const badge = screen.getByText('P1')
      expect(badge).toHaveClass('bg-red-500/10')
    })

    it('should show yellow badge for priority 2-3', () => {
      const p2Feature = { ...mockFeature, priority: 2 }
      renderWithQuery(<FeatureCard feature={p2Feature} />)

      const badge = screen.getByText('P2')
      expect(badge).toHaveClass('bg-yellow-500/10')
    })

    it('should show gray badge for priority > 3', () => {
      const p5Feature = { ...mockFeature, priority: 5 }
      renderWithQuery(<FeatureCard feature={p5Feature} />)

      const badge = screen.getByText('P5')
      expect(badge).toHaveClass('bg-gray-500/10')
    })
  })

  it('should apply custom className', () => {
    const { container } = renderWithQuery(
      <FeatureCard feature={mockFeature} className="custom-class" />
    )

    expect(container.firstChild).toHaveClass('custom-class')
  })
})
