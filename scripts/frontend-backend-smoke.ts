import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

function resolveApiBase(): string {
  if (process.env.API_BASE) return process.env.API_BASE;
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const apiTsPath = path.join(__dirname, '..', 'frontend', 'src', 'api.ts');
  try {
    const src = fs.readFileSync(apiTsPath, 'utf8');
    const match = src.match(/export const API_BASE[^]*?"([^"']+)"/);
    if (match) return match[1];
  } catch (err) {
    // ignore
  }
  return 'http://localhost:8000';
}

const API_BASE = resolveApiBase();

async function login(idToken: string): Promise<string> {
  const res = await fetch(`${API_BASE}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken })
  });
  if (!res.ok) {
    throw new Error(`Login failed: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as { access_token: string };
  return data.access_token;
}

function assert(condition: any, msg: string) {
  if (!condition) throw new Error(msg);
}

async function fetchJson<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    ...(init.headers as Record<string, string> | undefined)
  };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    throw new Error(`${init.method || 'GET'} ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function main() {
  console.log(`Using API_BASE=${API_BASE}`);
  const idToken = process.env.TEST_ID_TOKEN || 'test';
  const token = await login(idToken);

  const owners = await fetchJson<any[]>(token, '/owners');
  assert(Array.isArray(owners) && owners.length > 0, 'owners array empty');
  const owner = owners[0].owner;
  console.log('/owners ok');

  const groups = await fetchJson<any[]>(token, '/groups');
  assert(Array.isArray(groups), 'groups should be array');
  console.log('/groups ok');

  const portfolio = await fetchJson<any>(token, `/portfolio/${encodeURIComponent(owner)}`);
  assert(typeof portfolio === 'object', 'portfolio should be object');
  console.log('/portfolio/{owner} ok');

  const refresh = await fetchJson<{ status: string }>(token, '/prices/refresh', { method: 'POST' });
  assert(typeof refresh.status === 'string', 'price refresh missing status');
  console.log('/prices/refresh ok');

  console.log('Smoke tests completed successfully.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
