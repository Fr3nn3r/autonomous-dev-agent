import { useQuery } from '@tanstack/react-query'
import { Calendar, Clock, DollarSign, CheckCircle, Circle, AlertCircle, RefreshCw } from 'lucide-react'
import { apiClient, type TimelineFeature } from '../lib/api-client'

interface FeatureTimelineProps {
  className?: string
}

function formatDuration(hours: number): string {
  if (hours < 1) {
    return `${Math.round(hours * 60)}m`
  }
  if (hours < 24) {
    return `${hours.toFixed(1)}h`
  }
  return `${(hours / 24).toFixed(1)}d`
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-green-500'
    case 'in_progress':
      return 'bg-yellow-500'
    case 'blocked':
      return 'bg-red-500'
    default:
      return 'bg-gray-500'
  }
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
      return <Circle className="w-4 h-4 text-gray-500" />
  }
}

interface TimelineBarProps {
  feature: TimelineFeature
  earliestStart: Date | null
  latestEnd: Date | null
  timelineWidth: number
}

function TimelineBar({ feature, earliestStart, latestEnd, timelineWidth }: TimelineBarProps) {
  if (!earliestStart || !latestEnd || !feature.started_at) {
    return (
      <div className="h-6 flex items-center">
        <span className="text-xs text-gray-500 italic">Not started</span>
      </div>
    )
  }

  const totalMs = latestEnd.getTime() - earliestStart.getTime()
  if (totalMs <= 0) return null

  const featureStart = new Date(feature.started_at)
  const featureEnd = feature.completed_at
    ? new Date(feature.completed_at)
    : feature.sessions.length > 0 && feature.sessions[feature.sessions.length - 1].ended_at
      ? new Date(feature.sessions[feature.sessions.length - 1].ended_at!)
      : new Date()

  const startPercent = ((featureStart.getTime() - earliestStart.getTime()) / totalMs) * 100
  const widthPercent = ((featureEnd.getTime() - featureStart.getTime()) / totalMs) * 100

  return (
    <div className="h-6 relative" style={{ width: `${timelineWidth}px` }}>
      <div
        className={`absolute h-full rounded ${getStatusColor(feature.status)} opacity-50`}
        style={{
          left: `${startPercent}%`,
          width: `${Math.max(widthPercent, 1)}%`,
        }}
      />
      {/* Session segments */}
      {feature.sessions.map((session, idx) => {
        if (!session.started_at) return null
        const sessionStart = new Date(session.started_at)
        const sessionEnd = session.ended_at ? new Date(session.ended_at) : new Date()
        const sessionStartPercent = ((sessionStart.getTime() - earliestStart.getTime()) / totalMs) * 100
        const sessionWidthPercent = ((sessionEnd.getTime() - sessionStart.getTime()) / totalMs) * 100

        const sessionColor = session.outcome === 'success'
          ? 'bg-green-500'
          : session.outcome === 'failure'
            ? 'bg-red-500'
            : session.outcome === 'handoff'
              ? 'bg-yellow-500'
              : 'bg-gray-500'

        return (
          <div
            key={session.session_id || idx}
            className={`absolute h-3 top-1.5 rounded-sm ${sessionColor}`}
            style={{
              left: `${sessionStartPercent}%`,
              width: `${Math.max(sessionWidthPercent, 0.5)}%`,
            }}
            title={`Session: ${session.outcome} ($${session.cost_usd.toFixed(4)})`}
          />
        )
      })}
    </div>
  )
}

export function FeatureTimeline({ className = '' }: FeatureTimelineProps) {
  const { data: timeline, isLoading, error } = useQuery({
    queryKey: ['timeline'],
    queryFn: apiClient.getTimeline,
    refetchInterval: 30000,
  })

  if (isLoading) {
    return (
      <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            Feature Timeline
          </h2>
        </div>
        <div className="p-4">
          <div className="animate-pulse space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-700 rounded" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error || !timeline) {
    return (
      <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            Feature Timeline
          </h2>
        </div>
        <div className="p-4 text-gray-400 text-center">
          Unable to load timeline
        </div>
      </div>
    )
  }

  const earliestStart = timeline.earliest_start ? new Date(timeline.earliest_start) : null
  const latestEnd = timeline.latest_end ? new Date(timeline.latest_end) : null
  const timelineWidth = 300 // Fixed width for timeline bars

  const hasTimeData = earliestStart && latestEnd

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
      <div className="px-4 py-3 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5 text-primary-500" />
            Feature Timeline
          </h2>
          {hasTimeData && (
            <span className="text-xs text-gray-400">
              {formatDate(timeline.earliest_start)} - {formatDate(timeline.latest_end)}
            </span>
          )}
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        {timeline.features.length === 0 ? (
          <p className="text-gray-400 text-center py-4">No features in backlog</p>
        ) : (
          <div className="space-y-2">
            {timeline.features.map(feature => (
              <div
                key={feature.id}
                className="flex items-center gap-4 p-2 bg-gray-700/30 rounded hover:bg-gray-700/50 transition-colors"
              >
                {/* Feature Info */}
                <div className="w-48 shrink-0">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(feature.status)}
                    <span className="font-medium truncate" title={feature.name}>
                      {feature.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400 mt-1">
                    {feature.sessions.length > 0 && (
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDuration(feature.total_duration_hours)}
                      </span>
                    )}
                    {feature.total_cost_usd > 0 && (
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3" />
                        ${feature.total_cost_usd.toFixed(4)}
                      </span>
                    )}
                    {feature.sessions.length > 0 && (
                      <span>
                        {feature.sessions.length} session{feature.sessions.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>

                {/* Timeline Bar */}
                <TimelineBar
                  feature={feature}
                  earliestStart={earliestStart}
                  latestEnd={latestEnd}
                  timelineWidth={timelineWidth}
                />
              </div>
            ))}
          </div>
        )}

        {/* Legend */}
        {timeline.features.length > 0 && (
          <div className="flex items-center gap-4 mt-4 pt-4 border-t border-gray-700 text-xs text-gray-400">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-green-500" />
              <span>Success</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-yellow-500" />
              <span>Handoff</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-red-500" />
              <span>Failure</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-gray-500" />
              <span>Pending</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
