import { useEffect, useState } from "react";
import { API_BASE, setAuthToken } from "./api";
import { useAuth } from "./AuthContext";

interface Props {
  clientId: string;
  onSuccess: () => void;
}

declare global {
  interface Window {
    google: any;
  }
}

function sanitize(input: string): string {
  return new DOMParser().parseFromString(input, 'text/html').body
    .textContent || ''
}

export default function LoginPage({ clientId, onSuccess }: Props) {
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
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
            try {
              const payload = JSON.parse(
                atob(resp.credential.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
              );
              setUser({
                email: payload.email,
                name: payload.name,
                picture: payload.picture,
              });
            } catch (e) {
              console.error("Failed to decode Google credential", e);
            }
            onSuccess();
          } else {
            let msg = "Login failed";
            try {
              const err = await res.json();
              msg = err.detail || msg;
            } catch {
              // ignore JSON parse errors
            }
            setError(sanitize(msg));
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
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        marginTop: "2rem",
      }}
    >
      {error && (
        <div style={{ color: "red", marginBottom: "1rem" }}>{error}</div>
      )}
      <div id="google-signin"></div>
    </div>
  );
}
