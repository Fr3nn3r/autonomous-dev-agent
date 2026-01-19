import { useQuery } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import {
  Activity,
  CheckCircle,
  Clock,
  DollarSign,
  RefreshCw,
  Zap
} from 'lucide-react'
import { apiClient } from './lib/api-client'
import { useWebSocketContext } from './contexts/WebSocketContext'
import { CostProjections } from './components/CostProjections'
import { FeatureTimeline } from './components/FeatureTimeline'
import { AlertCenter } from './components/AlertCenter'
import { ThemeToggle } from './components/ThemeToggle'
import { FeatureCard } from './components/FeatureCard'
import { LogViewer } from './components/LogViewer'

function App() {
  const { isConnected, lastEvent } = useWebSocketContext()
  const [expandedFeatures, setExpandedFeatures] = useState<Set<string>>(new Set())

  // Fetch data with React Query
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['status'],
    queryFn: apiClient.getStatus,
  })

  const { data: backlog, isLoading: backlogLoading } = useQuery({
    queryKey: ['backlog'],
    queryFn: apiClient.getBacklog,
  })

  const { data: costs, isLoading: costsLoading } = useQuery({
    queryKey: ['costs'],
    queryFn: () => apiClient.getCostSummary(),
  })

  // Toggle feature expansion
  const handleFeatureToggle = useCallback((featureId: string) => {
    setExpandedFeatures(prev => {
      const next = new Set(prev)
      if (next.has(featureId)) {
        next.delete(featureId)
      } else {
        next.add(featureId)
      }
      return next
    })
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-white">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Zap className="w-8 h-8 text-primary-500" />
            <div>
              <h1 className="text-xl font-bold">ADA Dashboard</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {status?.project_name || 'Autonomous Dev Agent'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <AlertCenter />
            <div className={`flex items-center gap-2 text-sm ${isConnected ? 'text-green-500' : 'text-red-500'}`}>
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              {isConnected ? 'Connected' : 'Disconnected'}
            </div>
          </div>
        </div>
      </header>

      <main className="p-6">
        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatusCard
            icon={<Activity className="w-5 h-5" />}
            label="Status"
            value={status?.is_running ? 'Running' : 'Idle'}
            color={status?.is_running ? 'green' : 'gray'}
            loading={statusLoading}
          />
          <StatusCard
            icon={<CheckCircle className="w-5 h-5" />}
            label="Features"
            value={`${status?.features_completed || 0} / ${status?.features_total || 0}`}
            color="blue"
            loading={statusLoading}
          />
          <StatusCard
            icon={<Clock className="w-5 h-5" />}
            label="Sessions"
            value={String(status?.total_sessions || 0)}
            color="purple"
            loading={statusLoading}
          />
          <StatusCard
            icon={<DollarSign className="w-5 h-5" />}
            label="Total Cost"
            value={`$${costs?.total_cost_usd?.toFixed(4) || '0.00'}`}
            color="yellow"
            loading={costsLoading}
          />
        </div>

        {/* Current Session */}
        {status?.is_running && (
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 mb-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-primary-500" />
              Current Session
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-500 dark:text-gray-400">Feature:</span>
                <p className="font-medium">{status.current_feature_name || 'N/A'}</p>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Session ID:</span>
                <p className="font-medium font-mono">{status.current_session_id || 'N/A'}</p>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Context Usage:</span>
                <p className="font-medium">{status.context_usage_percent?.toFixed(1)}%</p>
              </div>
            </div>
            {/* Context progress bar */}
            <div className="mt-4">
              <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-500 ${
                    (status.context_usage_percent || 0) > 70 ? 'bg-yellow-500' : 'bg-primary-500'
                  }`}
                  style={{ width: `${status.context_usage_percent || 0}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Backlog */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold">Feature Backlog</h2>
            </div>
            <div className="p-4">
              {backlogLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded" />
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {backlog?.features.map(feature => (
                    <FeatureCard
                      key={feature.id}
                      feature={feature}
                      isExpanded={expandedFeatures.has(feature.id)}
                      onToggle={handleFeatureToggle}
                    />
                  ))}
                  {backlog?.features.length === 0 && (
                    <p className="text-gray-500 dark:text-gray-400 text-center py-4">No features in backlog</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Cost Breakdown */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold">Cost Breakdown</h2>
            </div>
            <div className="p-4">
              {costsLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-10 bg-gray-200 dark:bg-gray-700 rounded" />
                  ))}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="bg-gray-100 dark:bg-gray-700/50 rounded p-3">
                      <p className="text-gray-500 dark:text-gray-400">Input Tokens</p>
                      <p className="text-lg font-semibold">
                        {formatTokens(costs?.total_input_tokens || 0)}
                      </p>
                    </div>
                    <div className="bg-gray-100 dark:bg-gray-700/50 rounded p-3">
                      <p className="text-gray-500 dark:text-gray-400">Output Tokens</p>
                      <p className="text-lg font-semibold">
                        {formatTokens(costs?.total_output_tokens || 0)}
                      </p>
                    </div>
                  </div>

                  {costs?.cost_by_model && Object.keys(costs.cost_by_model).length > 0 && (
                    <div>
                      <h3 className="text-sm text-gray-500 dark:text-gray-400 mb-2">By Model</h3>
                      <div className="space-y-2">
                        {Object.entries(costs.cost_by_model).map(([model, cost]) => (
                          <div key={model} className="flex justify-between items-center text-sm">
                            <span className="text-gray-600 dark:text-gray-300 truncate">{model}</span>
                            <span className="font-medium">${cost.toFixed(4)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {costs?.sessions_by_outcome && Object.keys(costs.sessions_by_outcome).length > 0 && (
                    <div>
                      <h3 className="text-sm text-gray-500 dark:text-gray-400 mb-2">By Outcome</h3>
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(costs.sessions_by_outcome).map(([outcome, count]) => (
                          <span
                            key={outcome}
                            className={`px-2 py-1 rounded text-xs font-medium ${
                              outcome === 'success' ? 'bg-green-500/20 text-green-600 dark:text-green-400' :
                              outcome === 'failure' ? 'bg-red-500/20 text-red-600 dark:text-red-400' :
                              outcome === 'handoff' ? 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400' :
                              'bg-gray-500/20 text-gray-600 dark:text-gray-400'
                            }`}
                          >
                            {outcome}: {count}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Cost Projections & Log Viewer Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <CostProjections />
          <LogViewer />
        </div>

        {/* Feature Timeline */}
        <FeatureTimeline className="mt-6" />

        {/* Recent Events */}
        {lastEvent && (
          <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm text-gray-500 dark:text-gray-400 mb-2">Last Event</h3>
            <div className="font-mono text-sm">
              <span className="text-primary-500">{lastEvent.event}</span>
              <span className="text-gray-400 dark:text-gray-500 ml-2">
                {new Date(lastEvent.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

// Helper components

interface StatusCardProps {
  icon: React.ReactNode
  label: string
  value: string
  color: 'green' | 'blue' | 'purple' | 'yellow' | 'gray' | 'red'
  loading?: boolean
}

function StatusCard({ icon, label, value, color, loading }: StatusCardProps) {
  const colorClasses = {
    green: 'bg-green-500/10 text-green-600 dark:text-green-500 border-green-500/30',
    blue: 'bg-blue-500/10 text-blue-600 dark:text-blue-500 border-blue-500/30',
    purple: 'bg-purple-500/10 text-purple-600 dark:text-purple-500 border-purple-500/30',
    yellow: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-500 border-yellow-500/30',
    gray: 'bg-gray-500/10 text-gray-600 dark:text-gray-500 border-gray-500/30',
    red: 'bg-red-500/10 text-red-600 dark:text-red-500 border-red-500/30',
  }

  return (
    <div className={`rounded-lg border p-4 ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      {loading ? (
        <div className="h-7 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-bold">{value}</p>
      )}
    </div>
  )
}

function formatTokens(count: number): string {
  if (count < 1000) return String(count)
  if (count < 1_000_000) return `${(count / 1000).toFixed(1)}K`
  return `${(count / 1_000_000).toFixed(2)}M`
}

export default App
