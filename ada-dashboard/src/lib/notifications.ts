/**
 * Browser notification utilities for the ADA Dashboard.
 */

export type NotificationSeverity = 'info' | 'warning' | 'error' | 'success'

interface NotificationOptions {
  title: string
  message: string
  severity?: NotificationSeverity
  onClick?: () => void
}

/**
 * Check if browser notifications are supported.
 */
export function isNotificationSupported(): boolean {
  return 'Notification' in window
}

/**
 * Check if notifications are permitted.
 */
export function isNotificationPermitted(): boolean {
  return isNotificationSupported() && Notification.permission === 'granted'
}

/**
 * Request notification permission from the user.
 * Returns true if permission was granted.
 */
export async function requestNotificationPermission(): Promise<boolean> {
  if (!isNotificationSupported()) {
    return false
  }

  if (Notification.permission === 'granted') {
    return true
  }

  if (Notification.permission === 'denied') {
    return false
  }

  const permission = await Notification.requestPermission()
  return permission === 'granted'
}

/**
 * Get the notification icon based on severity.
 */
function getNotificationIcon(severity: NotificationSeverity): string {
  // Use data URLs for simple icons
  // In a real app, these would be actual icon URLs
  const icons: Record<NotificationSeverity, string> = {
    success: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%2322c55e"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>',
    warning: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23eab308"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>',
    error: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23ef4444"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>',
    info: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%233b82f6"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>',
  }
  return icons[severity]
}

/**
 * Show a browser notification.
 * Will request permission if not already granted.
 */
export async function showNotification(options: NotificationOptions): Promise<Notification | null> {
  const { title, message, severity = 'info', onClick } = options

  if (!isNotificationSupported()) {
    console.warn('Browser notifications are not supported')
    return null
  }

  // Request permission if needed
  if (Notification.permission === 'default') {
    const granted = await requestNotificationPermission()
    if (!granted) {
      return null
    }
  }

  if (Notification.permission !== 'granted') {
    return null
  }

  try {
    const notification = new Notification(`ADA: ${title}`, {
      body: message,
      icon: getNotificationIcon(severity),
      tag: `ada-${Date.now()}`, // Unique tag to prevent stacking
      requireInteraction: severity === 'error', // Keep error notifications visible
    })

    if (onClick) {
      notification.onclick = () => {
        onClick()
        notification.close()
        window.focus()
      }
    }

    // Auto-close non-error notifications after 5 seconds
    if (severity !== 'error') {
      setTimeout(() => notification.close(), 5000)
    }

    return notification
  } catch (error) {
    console.error('Failed to show notification:', error)
    return null
  }
}

/**
 * Create a notification handler for WebSocket events.
 */
export function createAlertNotificationHandler() {
  return async (alertData: {
    title: string
    message: string
    severity: NotificationSeverity
  }) => {
    // Only show desktop notifications for warnings and errors
    if (alertData.severity === 'warning' || alertData.severity === 'error') {
      await showNotification({
        title: alertData.title,
        message: alertData.message,
        severity: alertData.severity,
      })
    }
  }
}
