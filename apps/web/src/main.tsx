import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ToastHost, pushToast } from './components/Toast'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
})

// Global error listener — fires for any query that throws.
// 4xx errors that go through request() already toast on 401/403/500;
// we suppress the redundant toast by checking the message.
queryClient.getQueryCache().subscribe(event => {
  if (event.type === 'updated' && event.action.type === 'error') {
    const err = event.action.error as Error | null
    if (!err) return
    const msg = err.message || ''
    if (/^(4\d\d|5\d\d) /.test(msg)) return
    pushToast({ kind: 'error', text: `加载失败：${msg}` })
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <ToastHost />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
