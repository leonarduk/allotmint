import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './styles/responsive.css'
import './i18n'
import { ConfigProvider } from './ConfigContext'
import ErrorBoundary from './components/ErrorBoundary'

const App = lazy(() => import('./App.tsx'))
const Support = lazy(() => import('./pages/Support'))
const VirtualPortfolio = lazy(() => import('./pages/VirtualPortfolio'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route
            path="/support"
            element={
              <ErrorBoundary>
                <Suspense fallback={<div>Loading...</div>}>
                  <Support />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/virtual"
            element={
              <ErrorBoundary>
                <Suspense fallback={<div>Loading...</div>}>
                  <VirtualPortfolio />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/*"
            element={
              <ErrorBoundary>
                <Suspense fallback={<div>Loading...</div>}>
                  <App />
                </Suspense>
              </ErrorBoundary>
            }
          />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>,
)
