import { Suspense } from "react";
import MainApp from "./MainApp";
import { RouteProvider } from "./RouteContext";

export default function App() {
  return (
    <RouteProvider>
      <Suspense fallback={<div>Loading...</div>}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
          <MainApp />
        </div>
      </Suspense>
    </RouteProvider>
  );
}
