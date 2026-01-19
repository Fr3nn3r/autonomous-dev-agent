import { useQuery } from '@tanstack/react-query'
import { Clock, DollarSign, GitCommit, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react'
import { apiClient, type Session } from '../lib/api-client'
import { formatDistanceToNow } from 'date-fns'

interface SessionHistoryProps {
  featureId: string
  className?: string
}

function formatDuration(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt) return '-'
  const start = new Date(startedAt)
  const end = endedAt ? new Date(endedAt) : new Date()
  const durationMs = end.getTime() - start.getTime()

  const minutes = Math.floor(durationMs / 60000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

function getOutcomeIcon(outcome: string) {
  switch (outcome) {
    case 'success':
      return <CheckCircle className="w-4 h-4 text-green-500" />
    case 'failure':
      return <AlertCircle className="w-4 h-4 text-red-500" />
    case 'handoff':
      return <RefreshCw className="w-4 h-4 text-yellow-500" />
    default:
      return <Clock className="w-4 h-4 text-gray-400" />
  }
}

function getOutcomeBadgeColor(outcome: string): string {
  switch (outcome) {
    case 'success':
      return 'bg-green-500/10 text-green-600 dark:text-green-400'
    case 'failure':
      return 'bg-red-500/10 text-red-600 dark:text-red-400'
    case 'handoff':
      return 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'
    default:
      return 'bg-gray-500/10 text-gray-600 dark:text-gray-400'
  }
}

function SessionItem({ session }: { session: Session }) {
  const timeAgo = session.started_at
    ? formatDistanceToNow(new Date(session.started_at), { addSuffix: true })
    : 'Unknown'

  return (
    <div className="p-3 bg-gray-100 dark:bg-gray-700/50 rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {getOutcomeIcon(session.outcome)}
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${getOutcomeBadgeColor(session.outcome)}`}>
            {session.outcome}
          </span>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {timeAgo}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex items-center gap-1 text-gray-600 dark:text-gray-400">
          <Clock className="w-3 h-3" />
          <span>{formatDuration(session.started_at, session.ended_at)}</span>
        </div>
        <div className="flex items-center gap-1 text-gray-600 dark:text-gray-400">
          <DollarSign className="w-3 h-3" />
          <span>${session.cost_usd.toFixed(4)}</span>
        </div>
      </div>

      {session.commit_hash && (
        <div className="mt-2 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
          <GitCommit className="w-3 h-3" />
          <code className="font-mono">{session.commit_hash.slice(0, 7)}</code>
        </div>
      )}

      {session.error_message && (
        <div className="mt-2 p-2 bg-red-500/10 rounded text-xs text-red-600 dark:text-red-400">
          {session.error_message}
        </div>
      )}

      {session.files_changed.length > 0 && (
        <div className="mt-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {session.files_changed.length} file{session.files_changed.length !== 1 ? 's' : ''} changed
          </span>
        </div>
      )}
    </div>
  )
}

export function SessionHistory({ featureId, className = '' }: SessionHistoryProps) {
  const { data: sessionsData, isLoading, error } = useQuery({
    queryKey: ['sessions', 'feature', featureId],
    queryFn: () => apiClient.getSessions({ featureId, pageSize: 10 }),
    enabled: !!featureId,
  })

  if (isLoading) {
    return (
      <div className={`${className}`}>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Session History
        </h4>
        <div className="animate-pulse space-y-2">
          {[1, 2].map(i => (
            <div key={i} className="h-20 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`${className}`}>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Session History
        </h4>
        <div className="p-3 bg-red-500/10 rounded-lg text-sm text-red-600 dark:text-red-400">
          Failed to load sessions
        </div>
      </div>
    )
  }

  const sessions = sessionsData?.sessions || []

  if (sessions.length === 0) {
    return (
      <div className={`${className}`}>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Session History
        </h4>
        <div className="p-3 bg-gray-100 dark:bg-gray-700/50 rounded-lg text-sm text-gray-500 dark:text-gray-400 text-center">
          No sessions yet
        </div>
      </div>
    )
  }

  return (
    <div className={`${className}`}>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        Session History ({sessions.length})
      </h4>
      <div className="space-y-2">
        {sessions.map(session => (
          <SessionItem key={session.session_id} session={session} />
        ))}
      </div>
    </div>
  )
}

export default SessionHistory
