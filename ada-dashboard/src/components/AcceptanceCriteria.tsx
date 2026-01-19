import { CheckCircle, Circle } from 'lucide-react'

interface AcceptanceCriteriaProps {
  criteria: string[]
  completedCriteria?: string[]
  className?: string
}

export function AcceptanceCriteria({
  criteria,
  completedCriteria = [],
  className = '',
}: AcceptanceCriteriaProps) {
  if (criteria.length === 0) {
    return null
  }

  // Create a set for fast lookup
  const completedSet = new Set(completedCriteria)

  return (
    <div className={className}>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Acceptance Criteria
      </h4>
      <ul className="space-y-1.5">
        {criteria.map((criterion, index) => {
          const isCompleted = completedSet.has(criterion)
          return (
            <li
              key={index}
              className="flex items-start gap-2 text-sm"
            >
              {isCompleted ? (
                <CheckCircle className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
              ) : (
                <Circle className="w-4 h-4 text-gray-400 dark:text-gray-500 shrink-0 mt-0.5" />
              )}
              <span className={`${isCompleted ? 'text-gray-500 dark:text-gray-400 line-through' : 'text-gray-700 dark:text-gray-300'}`}>
                {criterion}
              </span>
            </li>
          )
        })}
      </ul>
      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {completedCriteria.length} / {criteria.length} completed
      </div>
    </div>
  )
}

export default AcceptanceCriteria
