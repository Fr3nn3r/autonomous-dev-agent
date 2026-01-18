import { useQuery } from '@tanstack/react-query'
import { TrendingUp, Calendar, AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react'
import { apiClient, type Projection } from '../lib/api-client'

interface CostProjectionsProps {
  className?: string
}

export function CostProjections({ className = '' }: CostProjectionsProps) {
  const { data: projection, isLoading, error } = useQuery({
    queryKey: ['projections'],
    queryFn: apiClient.getProjections,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  if (isLoading) {
    return (
      <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Cost Projections
          </h2>
        </div>
        <div className="p-4">
          <div className="animate-pulse space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-12 bg-gray-700 rounded" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error || !projection) {
    return (
      <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
        <div className="px-4 py-3 border-b border-gray-700">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Cost Projections
          </h2>
        </div>
        <div className="p-4 text-gray-400 text-center">
          Unable to load projections
        </div>
      </div>
    )
  }

  const confidenceColors = {
    low: 'text-red-400 bg-red-500/10',
    medium: 'text-yellow-400 bg-yellow-500/10',
    high: 'text-green-400 bg-green-500/10',
  }

  const ConfidenceIcon = {
    low: AlertTriangle,
    medium: HelpCircle,
    high: CheckCircle2,
  }[projection.confidence]

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 ${className}`}>
      <div className="px-4 py-3 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary-500" />
            Cost Projections
          </h2>
          <span className={`px-2 py-1 rounded text-xs font-medium flex items-center gap-1 ${confidenceColors[projection.confidence]}`}>
            <ConfidenceIcon className="w-3 h-3" />
            {projection.confidence} confidence
          </span>
        </div>
      </div>
      <div className="p-4 space-y-4">
        {/* Feature Progress */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-700/50 rounded p-3">
            <p className="text-gray-400 text-sm">Features Completed</p>
            <p className="text-2xl font-bold text-green-400">{projection.features_completed}</p>
          </div>
          <div className="bg-gray-700/50 rounded p-3">
            <p className="text-gray-400 text-sm">Features Remaining</p>
            <p className="text-2xl font-bold text-blue-400">{projection.features_remaining}</p>
          </div>
        </div>

        {/* Cost Stats */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Total Spent</span>
            <span className="font-medium">${projection.total_spent.toFixed(2)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Avg Cost/Feature</span>
            <span className="font-medium">${projection.avg_cost_per_feature.toFixed(4)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400">Daily Burn (7d)</span>
            <span className="font-medium">${projection.daily_burn_rate_7d.toFixed(4)}/day</span>
          </div>
        </div>

        {/* Projected Remaining Cost */}
        {projection.features_remaining > 0 && projection.projected_remaining_cost_mid > 0 && (
          <div className="bg-gray-700/50 rounded p-3">
            <p className="text-gray-400 text-sm mb-2">Projected Remaining Cost</p>
            <div className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-green-400">Best case</span>
                <span>${projection.projected_remaining_cost_low.toFixed(2)}</span>
              </div>
              <div className="flex justify-between font-medium">
                <span className="text-blue-400">Expected</span>
                <span className="text-lg">${projection.projected_remaining_cost_mid.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-yellow-400">Worst case</span>
                <span>${projection.projected_remaining_cost_high.toFixed(2)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Estimated Completion */}
        {projection.estimated_completion_date_mid && (
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Calendar className="w-4 h-4" />
            <span>Est. completion: {projection.estimated_completion_date_mid}</span>
          </div>
        )}

        {/* All Features Done */}
        {projection.features_remaining === 0 && (
          <div className="flex items-center gap-2 text-green-400 bg-green-500/10 rounded p-3">
            <CheckCircle2 className="w-5 h-5" />
            <span className="font-medium">All features completed!</span>
          </div>
        )}
      </div>
    </div>
  )
}
