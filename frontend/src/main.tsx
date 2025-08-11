import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import './index.css'
import './i18n'
import App from './App.tsx'
import Support from './pages/Support'
import VirtualPortfolio from './pages/VirtualPortfolio'

import { NavigationBar } from './components/NavigationBar'
import AdminConfig from './pages/AdminConfig'
import './i18n'
import { ConfigProvider } from './ConfigContext'

export function Layout() {
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <NavigationBar />
      <Outlet />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/support" element={<Support />} />
          <Route path="/virtual" element={<VirtualPortfolio />} />
          <Route path="/admin/config" element={<AdminConfig />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>,
)
