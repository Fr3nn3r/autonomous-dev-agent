import { useState } from 'react'
import {
  CheckCircle,
  Circle,
  AlertCircle,
  RefreshCw,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { type Feature } from '../lib/api-client'
import { FeatureDetails } from './FeatureDetails'

interface FeatureCardProps {
  feature: Feature
  isExpanded?: boolean
  onToggle?: (featureId: string) => void
  className?: string
}

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-4 h-4 text-green-500" />
    case 'in_progress':
      return <RefreshCw className="w-4 h-4 text-yellow-500 animate-spin" />
    case 'blocked':
      return <AlertCircle className="w-4 h-4 text-red-500" />
    default:
      return <Circle className="w-4 h-4 text-gray-400 dark:text-gray-500" />
  }
}

function getPriorityBadge(priority: number) {
  if (priority <= 1) {
    return (
      <span className="px-1.5 py-0.5 bg-red-500/10 text-red-600 dark:text-red-400 text-xs rounded font-medium">
        P{priority}
      </span>
    )
  }
  if (priority <= 3) {
    return (
      <span className="px-1.5 py-0.5 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 text-xs rounded font-medium">
        P{priority}
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 bg-gray-500/10 text-gray-600 dark:text-gray-400 text-xs rounded font-medium">
      P{priority}
    </span>
  )
}

export function FeatureCard({
  feature,
  isExpanded: controlledExpanded,
  onToggle,
  className = '',
}: FeatureCardProps) {
  // Allow both controlled and uncontrolled usage
  const [internalExpanded, setInternalExpanded] = useState(false)
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded

  const handleToggle = () => {
    if (onToggle) {
      onToggle(feature.id)
    } else {
      setInternalExpanded(!internalExpanded)
    }
  }

  return (
    <div
      className={`bg-gray-100 dark:bg-gray-700/50 rounded-lg overflow-hidden transition-colors hover:bg-gray-200/70 dark:hover:bg-gray-700/70 ${className}`}
    >
      {/* Collapsed Header - always visible */}
      <button
        onClick={handleToggle}
        className="w-full p-3 text-left flex items-start gap-3"
      >
        {/* Status Icon */}
        <div className="mt-0.5 shrink-0">
          {getStatusIcon(feature.status)}
        </div>

        {/* Main Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-medium truncate">{feature.name}</h3>
            <div className="flex items-center gap-2 shrink-0">
              {getPriorityBadge(feature.priority)}
              {feature.sessions_spent > 0 && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {feature.sessions_spent} session{feature.sessions_spent !== 1 ? 's' : ''}
                </span>
              )}
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-400" />
              )}
            </div>
          </div>
          {!isExpanded && (
            <p className="text-sm text-gray-500 dark:text-gray-400 truncate mt-0.5">
              {feature.description}
            </p>
          )}
        </div>
      </button>

      {/* Expandable Details */}
      <div className={`feature-details-grid ${isExpanded ? 'expanded' : ''}`}>
        <div className="feature-details-content">
          {isExpanded && (
            <div className="px-3 pb-3 pt-0 border-t border-gray-200 dark:border-gray-600">
              <FeatureDetails feature={feature} className="pt-3" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default FeatureCard
