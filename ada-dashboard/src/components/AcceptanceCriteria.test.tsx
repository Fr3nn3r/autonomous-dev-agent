import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AcceptanceCriteria } from './AcceptanceCriteria'

describe('AcceptanceCriteria', () => {
  it('should render nothing when criteria is empty', () => {
    const { container } = render(<AcceptanceCriteria criteria={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('should render all criteria items', () => {
    const criteria = [
      'User can log in',
      'User can log out',
      'User sees dashboard',
    ]

    render(<AcceptanceCriteria criteria={criteria} />)

    expect(screen.getByText('User can log in')).toBeInTheDocument()
    expect(screen.getByText('User can log out')).toBeInTheDocument()
    expect(screen.getByText('User sees dashboard')).toBeInTheDocument()
  })

  it('should show header text', () => {
    render(<AcceptanceCriteria criteria={['Test criterion']} />)

    expect(screen.getByText('Acceptance Criteria')).toBeInTheDocument()
  })

  it('should show completion count', () => {
    const criteria = ['Item 1', 'Item 2', 'Item 3']
    const completed = ['Item 1']

    render(<AcceptanceCriteria criteria={criteria} completedCriteria={completed} />)

    expect(screen.getByText('1 / 3 completed')).toBeInTheDocument()
  })

  it('should show 0 completed when no completedCriteria provided', () => {
    const criteria = ['Item 1', 'Item 2']

    render(<AcceptanceCriteria criteria={criteria} />)

    expect(screen.getByText('0 / 2 completed')).toBeInTheDocument()
  })

  it('should apply strikethrough to completed items', () => {
    const criteria = ['Completed item', 'Pending item']
    const completed = ['Completed item']

    render(<AcceptanceCriteria criteria={criteria} completedCriteria={completed} />)

    const completedItem = screen.getByText('Completed item')
    expect(completedItem).toHaveClass('line-through')

    const pendingItem = screen.getByText('Pending item')
    expect(pendingItem).not.toHaveClass('line-through')
  })

  it('should apply custom className', () => {
    const { container } = render(
      <AcceptanceCriteria criteria={['Test']} className="custom-class" />
    )

    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('should handle all items completed', () => {
    const criteria = ['Item 1', 'Item 2']
    const completed = ['Item 1', 'Item 2']

    render(<AcceptanceCriteria criteria={criteria} completedCriteria={completed} />)

    expect(screen.getByText('2 / 2 completed')).toBeInTheDocument()
  })
})
