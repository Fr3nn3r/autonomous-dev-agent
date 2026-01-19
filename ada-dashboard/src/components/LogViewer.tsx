import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Terminal, Search, Clock, Pause, Play, ChevronDown } from 'lucide-react'
import { apiClient } from '../lib/api-client'
import { useWebSocketEvent } from '../contexts/WebSocketContext'

interface LogEntry {
  id: string
  timestamp: Date
  content: string
}

interface LogViewerProps {
  className?: string
  maxLines?: number
  showTimestamps?: boolean
  showFilter?: boolean
}

const MAX_BUFFER_SIZE = 500

export function LogViewer({
  className = '',
  maxLines = 500,
  showTimestamps = true,
  showFilter = true,
}: LogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [isPaused, setIsPaused] = useState(false)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const shouldScrollRef = useRef(true)
  const logIdCounterRef = useRef(0)

  // Load initial logs from API
  const { data: initialProgress } = useQuery({
    queryKey: ['progress', 'initial'],
    queryFn: () => apiClient.getProgress(100),
    staleTime: Infinity, // Only fetch once
    refetchOnWindowFocus: false,
  })

  // Initialize logs from API response
  useEffect(() => {
    if (initialProgress?.content) {
      const lines = initialProgress.content.split('\n').filter(line => line.trim())
      const initialLogs: LogEntry[] = lines.map((content, index) => ({
        id: `initial-${index}`,
        timestamp: new Date(),
        content,
      }))
      setLogs(initialLogs.slice(-maxLines))
    }
  }, [initialProgress, maxLines])

  // Handle new log entries from WebSocket
  const handleProgressUpdate = useCallback((data: Record<string, unknown>) => {
    if (isPaused) return

    const content = data.content as string || data.line as string || ''
    if (!content) return

    const newEntry: LogEntry = {
      id: `ws-${logIdCounterRef.current++}`,
      timestamp: new Date(),
      content,
    }

    setLogs(prev => {
      const updated = [...prev, newEntry]
      // Keep buffer under max size
      if (updated.length > MAX_BUFFER_SIZE) {
        return updated.slice(-maxLines)
      }
      return updated
    })
  }, [isPaused, maxLines])

  useWebSocketEvent('progress.update', handleProgressUpdate)

  // Auto-scroll logic
  useEffect(() => {
    if (!containerRef.current || !shouldScrollRef.current || !isAtBottom) return

    containerRef.current.scrollTop = containerRef.current.scrollHeight
  }, [logs, isAtBottom])

  // Handle scroll events to detect user scrolling away from bottom
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return

    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 50
    setIsAtBottom(isNearBottom)
    shouldScrollRef.current = isNearBottom
  }, [])

  // Scroll to bottom function
  const scrollToBottom = useCallback(() => {
    if (!containerRef.current) return
    containerRef.current.scrollTop = containerRef.current.scrollHeight
    setIsAtBottom(true)
    shouldScrollRef.current = true
  }, [])

  // Filter logs
  const filteredLogs = filter
    ? logs.filter(log => log.content.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 flex flex-col ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-primary-500" />
          <h2 className="text-lg font-semibold">Live Logs</h2>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            ({filteredLogs.length} lines)
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Pause/Play toggle */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`p-2 rounded-lg transition-colors ${
              isPaused
                ? 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/20'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
            title={isPaused ? 'Resume auto-update' : 'Pause auto-update'}
          >
            {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          </button>

          {/* Scroll to bottom button (shown when not at bottom) */}
          {!isAtBottom && (
            <button
              onClick={scrollToBottom}
              className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
              title="Scroll to bottom"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Filter bar */}
      {showFilter && (
        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter logs..."
              className="w-full pl-9 pr-4 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>
        </div>
      )}

      {/* Log content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 font-mono text-sm log-viewer-container"
        style={{ minHeight: '300px', maxHeight: '500px' }}
      >
        {filteredLogs.length === 0 ? (
          <div className="text-gray-400 dark:text-gray-500 text-center py-8">
            <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No log entries yet</p>
          </div>
        ) : (
          <div className="space-y-1">
            {filteredLogs.map((log) => (
              <div
                key={log.id}
                className="flex gap-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 -mx-2 px-2 py-0.5 rounded"
              >
                {showTimestamps && (
                  <span className="text-gray-400 dark:text-gray-500 shrink-0 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {log.timestamp.toLocaleTimeString()}
                  </span>
                )}
                <span className="whitespace-pre-wrap break-all">{log.content}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer status */}
      <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>
          {isPaused && (
            <span className="text-yellow-600 dark:text-yellow-400 font-medium">
              Paused -
            </span>
          )}{' '}
          {filteredLogs.length} / {logs.length} lines
          {filter && ` (filtered)`}
        </span>
        {!isAtBottom && (
          <span className="text-gray-400">
            Scroll paused - new entries buffered
          </span>
        )}
      </div>
    </div>
  )
}

export default LogViewer
