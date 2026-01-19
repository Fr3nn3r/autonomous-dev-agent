/**
 * API client for the ADA Dashboard backend.
 */

const API_BASE = '/api'

export interface HarnessStatus {
  project_path: string | null
  project_name: string | null
  is_running: boolean
  current_feature_id: string | null
  current_feature_name: string | null
  current_session_id: string | null
  context_usage_percent: number
  total_sessions: number
  features_completed: number
  features_total: number
  last_updated: string | null
}

export interface Feature {
  id: string
  name: string
  description: string
  category: string
  status: string
  priority: number
  sessions_spent: number
  depends_on: string[]
  acceptance_criteria: string[]
  implementation_notes: string[]
  model_override: string | null
}

export interface BacklogResponse {
  project_name: string
  project_path: string
  features: Feature[]
  total_features: number
  completed_features: number
  in_progress_features: number
  pending_features: number
  blocked_features: number
}

export interface Session {
  session_id: string
  feature_id: string | null
  started_at: string | null
  ended_at: string | null
  outcome: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  model: string
  cost_usd: number
  files_changed: string[]
  commit_hash: string | null
  error_message: string | null
  error_category: string | null
}

export interface SessionListResponse {
  sessions: Session[]
  total: number
  page: number
  page_size: number
}

export interface CostSummary {
  total_cost_usd: number
  total_sessions: number
  total_input_tokens: number
  total_output_tokens: number
  total_cache_read_tokens: number
  total_cache_write_tokens: number
  cost_by_model: Record<string, number>
  sessions_by_model: Record<string, number>
  sessions_by_outcome: Record<string, number>
  period_start: string | null
  period_end: string | null
}

export interface ProgressResponse {
  content: string
  lines: number
  total_lines: number
  file_size_kb: number
}

export interface Projection {
  avg_cost_per_feature: number
  features_remaining: number
  features_completed: number
  projected_remaining_cost_low: number
  projected_remaining_cost_mid: number
  projected_remaining_cost_high: number
  daily_burn_rate_7d: number
  estimated_completion_date_mid: string | null
  total_spent: number
  confidence: 'low' | 'medium' | 'high'
}

export interface SessionSegment {
  session_id: string
  started_at: string | null
  ended_at: string | null
  outcome: string
  cost_usd: number
}

export interface TimelineFeature {
  id: string
  name: string
  status: string
  started_at: string | null
  completed_at: string | null
  sessions: SessionSegment[]
  total_duration_hours: number
  total_cost_usd: number
}

export interface TimelineResponse {
  features: TimelineFeature[]
  earliest_start: string | null
  latest_end: string | null
}

export interface Alert {
  id: string
  type: string
  severity: 'info' | 'warning' | 'error' | 'success'
  title: string
  message: string
  timestamp: string
  read: boolean
  dismissed: boolean
  feature_id: string | null
  session_id: string | null
}

export interface AlertListResponse {
  alerts: Alert[]
  total: number
  unread_count: number
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`API Error ${response.status}: ${error}`)
  }

  return response.json()
}

export const apiClient = {
  /**
   * Get current harness status
   */
  async getStatus(): Promise<HarnessStatus> {
    return fetchJson<HarnessStatus>(`${API_BASE}/status`)
  },

  /**
   * Get feature backlog
   */
  async getBacklog(): Promise<BacklogResponse> {
    return fetchJson<BacklogResponse>(`${API_BASE}/backlog`)
  },

  /**
   * Get a specific feature
   */
  async getFeature(featureId: string): Promise<Feature> {
    return fetchJson<Feature>(`${API_BASE}/backlog/${featureId}`)
  },

  /**
   * Get session history
   */
  async getSessions(options?: {
    page?: number
    pageSize?: number
    featureId?: string
    outcome?: string
  }): Promise<SessionListResponse> {
    const params = new URLSearchParams()
    if (options?.page) params.set('page', String(options.page))
    if (options?.pageSize) params.set('page_size', String(options.pageSize))
    if (options?.featureId) params.set('feature_id', options.featureId)
    if (options?.outcome) params.set('outcome', options.outcome)

    return fetchJson<SessionListResponse>(`${API_BASE}/sessions?${params}`)
  },

  /**
   * Get a specific session
   */
  async getSession(sessionId: string): Promise<Session> {
    return fetchJson<Session>(`${API_BASE}/sessions/${sessionId}`)
  },

  /**
   * Get cost summary
   */
  async getCostSummary(days?: number): Promise<CostSummary> {
    const params = days ? `?days=${days}` : ''
    return fetchJson<CostSummary>(`${API_BASE}/sessions/costs${params}`)
  },

  /**
   * Get recent progress log entries
   */
  async getProgress(lines: number = 50, offset: number = 0): Promise<ProgressResponse> {
    return fetchJson<ProgressResponse>(`${API_BASE}/progress?lines=${lines}&offset=${offset}`)
  },

  /**
   * Get full progress log
   */
  async getFullProgress(): Promise<ProgressResponse> {
    return fetchJson<ProgressResponse>(`${API_BASE}/progress/full`)
  },

  /**
   * Get cost projections
   */
  async getProjections(): Promise<Projection> {
    return fetchJson<Projection>(`${API_BASE}/projections`)
  },

  /**
   * Get feature timeline
   */
  async getTimeline(): Promise<TimelineResponse> {
    return fetchJson<TimelineResponse>(`${API_BASE}/timeline`)
  },

  /**
   * Get alerts
   */
  async getAlerts(includeDismissed: boolean = false): Promise<AlertListResponse> {
    const params = includeDismissed ? '?include_dismissed=true' : ''
    return fetchJson<AlertListResponse>(`${API_BASE}/alerts${params}`)
  },

  /**
   * Get unread alert count
   */
  async getUnreadCount(): Promise<{ count: number }> {
    return fetchJson<{ count: number }>(`${API_BASE}/alerts/unread/count`)
  },

  /**
   * Mark alert as read
   */
  async markAlertRead(alertId: string): Promise<void> {
    await fetchJson<unknown>(`${API_BASE}/alerts/${alertId}/read`, { method: 'POST' })
  },

  /**
   * Mark all alerts as read
   */
  async markAllAlertsRead(): Promise<void> {
    await fetchJson<unknown>(`${API_BASE}/alerts/read-all`, { method: 'POST' })
  },

  /**
   * Dismiss an alert
   */
  async dismissAlert(alertId: string): Promise<void> {
    await fetchJson<unknown>(`${API_BASE}/alerts/${alertId}/dismiss`, { method: 'POST' })
  },
}

export default apiClient
