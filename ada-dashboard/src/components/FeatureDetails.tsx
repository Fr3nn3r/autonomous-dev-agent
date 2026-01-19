import { Link2, FileText, Calendar } from 'lucide-react'
import { type Feature } from '../lib/api-client'
import { AcceptanceCriteria } from './AcceptanceCriteria'
import { SessionHistory } from './SessionHistory'

interface FeatureDetailsProps {
  feature: Feature
  className?: string
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '-'
  }
}

export function FeatureDetails({ feature, className = '' }: FeatureDetailsProps) {
  return (
    <div className={`space-y-4 ${className}`}>
      {/* Full Description */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Description
        </h4>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {feature.description || 'No description provided'}
        </p>
      </div>

      {/* Acceptance Criteria */}
      {feature.acceptance_criteria && feature.acceptance_criteria.length > 0 && (
        <AcceptanceCriteria criteria={feature.acceptance_criteria} />
      )}

      {/* Implementation Notes */}
      {feature.implementation_notes && feature.implementation_notes.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            <FileText className="w-4 h-4 inline mr-1" />
            Implementation Notes
          </h4>
          <ul className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
            {feature.implementation_notes.map((note, index) => (
              <li key={index} className="flex items-start gap-2">
                <span className="text-gray-400 dark:text-gray-500">-</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Dependencies */}
      {feature.depends_on && feature.depends_on.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            <Link2 className="w-4 h-4 inline mr-1" />
            Dependencies
          </h4>
          <div className="flex flex-wrap gap-2">
            {feature.depends_on.map((depId) => (
              <span
                key={depId}
                className="px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded text-xs font-mono text-gray-600 dark:text-gray-400"
              >
                {depId}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Metadata Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <span className="text-gray-500 dark:text-gray-400 block text-xs">Category</span>
          <span className="font-medium">{feature.category || '-'}</span>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400 block text-xs">Priority</span>
          <span className="font-medium">{feature.priority}</span>
        </div>
        <div>
          <span className="text-gray-500 dark:text-gray-400 block text-xs">Sessions</span>
          <span className="font-medium">{feature.sessions_spent}</span>
        </div>
        {feature.model_override && (
          <div>
            <span className="text-gray-500 dark:text-gray-400 block text-xs">Model</span>
            <span className="font-medium font-mono text-xs">{feature.model_override}</span>
          </div>
        )}
      </div>

      {/* Session History - loaded lazily when expanded */}
      <SessionHistory featureId={feature.id} className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700" />
    </div>
  )
}

export default FeatureDetails
