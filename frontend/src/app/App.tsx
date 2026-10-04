import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'
import { AuthProvider } from '@/features/auth/AuthContext'
import { LoginPage } from '@/features/auth/LoginPage'
import { RedirectIfAuthenticated, RequireAuth } from '@/features/auth/RequireAuth'
import { SignupPage } from '@/features/auth/SignupPage'
import { ApiError } from '@/lib/api'
import { AppShell } from './layout/AppShell'

// Route-level code splitting keeps the charting library out of the initial bundle.
const BillsPage = lazy(() =>
  import('@/features/bills/BillsPage').then((m) => ({ default: m.BillsPage })),
)
const DashboardPage = lazy(() =>
  import('@/features/dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const BillReviewPage = lazy(() =>
  import('@/features/review/BillReviewPage').then((m) => ({ default: m.BillReviewPage })),
)
const ReviewQueuePage = lazy(() =>
  import('@/features/review/ReviewQueuePage').then((m) => ({ default: m.ReviewQueuePage })),
)
const UploadPage = lazy(() =>
  import('@/features/upload/UploadPage').then((m) => ({ default: m.UploadPage })),
)
const VendorsPage = lazy(() =>
  import('@/features/vendors/VendorsPage').then((m) => ({ default: m.VendorsPage })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // Never retry client errors (401/404/422); retry transient ones twice.
      retry: (count, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route
                path="/login"
                element={
                  <RedirectIfAuthenticated>
                    <LoginPage />
                  </RedirectIfAuthenticated>
                }
              />
              <Route
                path="/signup"
                element={
                  <RedirectIfAuthenticated>
                    <SignupPage />
                  </RedirectIfAuthenticated>
                }
              />
              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route index element={<DashboardPage />} />
                <Route path="upload" element={<UploadPage />} />
                <Route path="review" element={<ReviewQueuePage />} />
                <Route path="bills" element={<BillsPage />} />
                <Route path="bills/:invoiceId" element={<BillReviewPage />} />
                <Route path="vendors" element={<VendorsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
