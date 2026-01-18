import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bell,
  X,
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  Info,
  Check,
  Trash2
} from 'lucide-react'
import { apiClient, type Alert } from '../lib/api-client'

interface AlertCenterProps {
  className?: string
}

function getSeverityIcon(severity: string) {
  switch (severity) {
    case 'success':
      return <CheckCircle className="w-4 h-4 text-green-500" />
    case 'warning':
      return <AlertTriangle className="w-4 h-4 text-yellow-500" />
    case 'error':
      return <AlertCircle className="w-4 h-4 text-red-500" />
    default:
      return <Info className="w-4 h-4 text-blue-500" />
  }
}

function getSeverityBgColor(severity: string): string {
  switch (severity) {
    case 'success':
      return 'bg-green-500/10 border-green-500/30'
    case 'warning':
      return 'bg-yellow-500/10 border-yellow-500/30'
    case 'error':
      return 'bg-red-500/10 border-red-500/30'
    default:
      return 'bg-blue-500/10 border-blue-500/30'
  }
}

function formatTimeAgo(timestamp: string): string {
  const now = new Date()
  const date = new Date(timestamp)
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function AlertItem({
  alert,
  onMarkRead,
  onDismiss
}: {
  alert: Alert
  onMarkRead: (id: string) => void
  onDismiss: (id: string) => void
}) {
  return (
    <div
      className={`p-3 border rounded-lg ${getSeverityBgColor(alert.severity)} ${
        !alert.read ? 'border-l-4' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5">
          {getSeverityIcon(alert.severity)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className={`font-medium text-sm ${!alert.read ? 'text-white' : 'text-gray-300'}`}>
              {alert.title}
            </span>
            <span className="text-xs text-gray-500 shrink-0">
              {formatTimeAgo(alert.timestamp)}
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-1 line-clamp-2">
            {alert.message}
          </p>
        </div>
        <div className="flex gap-1 shrink-0">
          {!alert.read && (
            <button
              onClick={() => onMarkRead(alert.id)}
              className="p-1 text-gray-400 hover:text-white hover:bg-gray-600 rounded"
              title="Mark as read"
            >
              <Check className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => onDismiss(alert.id)}
            className="p-1 text-gray-400 hover:text-white hover:bg-gray-600 rounded"
            title="Dismiss"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function AlertCenter({ className = '' }: AlertCenterProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Fetch alerts
  const { data: alertsData } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiClient.getAlerts(false),
    refetchInterval: 10000, // Poll every 10 seconds
  })

  // Mark as read mutation
  const markReadMutation = useMutation({
    mutationFn: apiClient.markAlertRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  // Mark all as read mutation
  const markAllReadMutation = useMutation({
    mutationFn: apiClient.markAllAlertsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  // Dismiss mutation
  const dismissMutation = useMutation({
    mutationFn: apiClient.dismissAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Request browser notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  const alerts = alertsData?.alerts || []
  const unreadCount = alertsData?.unread_count || 0

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-96 max-h-[32rem] bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 flex flex-col">
          {/* Header */}
          <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
            <h3 className="font-semibold">Notifications</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={() => markAllReadMutation.mutate()}
                  className="text-xs text-primary-400 hover:text-primary-300"
                >
                  Mark all read
                </button>
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Alerts List */}
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {alerts.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <Bell className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No notifications</p>
              </div>
            ) : (
              alerts.map(alert => (
                <AlertItem
                  key={alert.id}
                  alert={alert}
                  onMarkRead={(id) => markReadMutation.mutate(id)}
                  onDismiss={(id) => dismissMutation.mutate(id)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
