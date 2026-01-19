import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from './contexts/ThemeContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import './index.css'
import App from './App'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000, // Refetch every 5 seconds
      staleTime: 2000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <App />
        </WebSocketProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
