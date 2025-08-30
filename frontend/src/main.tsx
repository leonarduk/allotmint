import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './i18n'
import App from './App.tsx'
import VirtualPortfolio from './pages/VirtualPortfolio'
import Reports from './pages/Reports'
import Support from './pages/Support'
import './i18n'
import { ConfigProvider } from './ConfigContext'
import { PriceRefreshProvider } from './PriceRefreshContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider>
      <PriceRefreshProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/support" element={<Support />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/virtual" element={<VirtualPortfolio />} />
            <Route path="/*" element={<App />} />
          </Routes>
        </BrowserRouter>
      </PriceRefreshProvider>
    </ConfigProvider>
  </StrictMode>,
)
