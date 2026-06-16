import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { API_BASE, setAuthToken } from './api';
import { useUser } from './UserContext';
import { useAuth } from './AuthContext';
import { signInWithCognito, type AwsUiAuthConfig } from './awsUiAuth';

interface Props {
  clientId: string;
  awsUiAuth?: AwsUiAuthConfig;
  onSuccess: () => void;
}

declare global {
  interface Window {
    google: any;
  }
}

function sanitize(input: string): string {
  return (
    new DOMParser().parseFromString(input, 'text/html').body.textContent || ''
  );
}

export default function LoginPage({ clientId, awsUiAuth, onSuccess }: Props) {
  const { setProfile } = useUser();
  const { setUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [cognitoError, setCognitoError] = useState<string | null>(null);
  const awsUiAuthEnabled =
    awsUiAuth?.enabled === true || awsUiAuth?.enabled === 'true';
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
    script.onload = () => {
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (resp: { credential: string }) => {
          const decoded = decodeJwt(resp.credential);
          setProfile({
            email: decoded.email,
            name: decoded.name,
            picture: decoded.picture,
          });

          const res = await fetch(`${API_BASE}/token/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: resp.credential }),
          });
          if (res.ok) {
            const data = await res.json();
            setAuthToken(data.access_token);
            try {
              const base64Url = resp.credential.split('.')[1];
              const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
              const padding = '='.repeat((4 - (base64.length % 4)) % 4);
              const payload = JSON.parse(atob(base64 + padding));
              setUser({
                email: payload.email,
                name: payload.name,
                picture: payload.picture,
              });
            } catch (e) {
              console.error('Failed to decode Google credential', e);
            }
            onSuccess();
          } else {
            let msg = 'Login failed';
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
        document.getElementById('google-signin'),
        { theme: 'outline', size: 'large' }
      );
    };
    return () => {
      document.head.removeChild(script);
    };
  }, [clientId, onSuccess, setProfile, setUser]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        marginTop: '2rem',
      }}
    >
      {error && (
        <div
          role="alert"
          aria-live="assertive"
          style={{ color: 'red', marginBottom: '1rem' }}
        >
          Error: {error}
        </div>
      )}
      <div id="google-signin"></div>
      {awsUiAuthEnabled && (
        <div style={{ marginTop: '1rem' }}>
          {cognitoError && (
            <div
              role="alert"
              aria-live="assertive"
              style={{ color: 'red', marginBottom: '0.5rem' }}
            >
              {cognitoError}
            </div>
          )}
          <button
            type="button"
            onClick={() => {
              setCognitoError(null);
              signInWithCognito(awsUiAuth).catch((err: unknown) => {
                console.error('Cognito sign-in initiation failed:', err);
                setCognitoError('Failed to start sign-in. Please try again.');
              });
            }}
          >
            Sign in
          </button>
        </div>
      )}
      <p style={{ marginTop: '1rem' }}>
        Don&apos;t have an account?{' '}
        <Link to="/create-account">Create account</Link>
      </p>
    </div>
  );
}

function decodeJwt(token: string) {
  const payload = token.split('.')[1];
  try {
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(base64);
    return JSON.parse(json);
  } catch {
    return {};
  }
}
