import { useEffect } from "react";
import { API_BASE, setAuthToken } from "./api";

interface Props {
  clientId: string;
  onSuccess: () => void;
}

declare global {
  interface Window {
    google: any;
  }
}

export default function LoginPage({ clientId, onSuccess }: Props) {
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
    script.onload = () => {
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (resp: { credential: string }) => {
          const res = await fetch(`${API_BASE}/token/google`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: resp.credential }),
          });
          if (res.ok) {
            const data = await res.json();
            setAuthToken(data.access_token);
            onSuccess();
          }
        },
      });
      window.google.accounts.id.renderButton(
        document.getElementById("google-signin"),
        { theme: "outline", size: "large" },
      );
    };
    return () => {
      document.head.removeChild(script);
    };
  }, [clientId, onSuccess]);

  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: "2rem" }}>
      <div id="google-signin"></div>
    </div>
  );
}
