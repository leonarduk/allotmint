import {StrictMode} from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter, Routes, Route} from "react-router-dom";
import "./index.css";
import "./styles/responsive.css";
import App from "./App.tsx";
import VirtualPortfolio from "./pages/VirtualPortfolio";
import "./i18n";
import {ConfigProvider} from "./ConfigContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider>
      <BrowserRouter
        future={{v7_startTransition: true, v7_relativeSplatPath: true}}
      >
        <Routes>
          <Route path="/virtual" element={<VirtualPortfolio />} />
          <Route path="/*" element={<App />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  </StrictMode>
);
