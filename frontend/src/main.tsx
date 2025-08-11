import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './i18n'
import App from './App.tsx'
import Support from './pages/Support'
import VirtualPortfolio from './pages/VirtualPortfolio'
import AdminConfig from './pages/AdminConfig'
import './i18n'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/support" element={<Support />} />
        <Route path="/virtual" element={<VirtualPortfolio />} />
        <Route path="/admin/config" element={<AdminConfig />} />
        <Route path="/*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
