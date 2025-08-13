import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './i18n'
import App from './App.tsx'
import './i18n'
import { ConfigProvider } from './ConfigContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/support" element={<App />} />
          <Route path="/virtual" element={<App />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>,
)
