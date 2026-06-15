const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
const DEFAULT_BASE_URL = isTauri ? 'http://127.0.0.1:18765' : 'http://127.0.0.1:8765';

export interface HealthPayload {
  status: 'ok';
  service: string;
}

export async function fetchHealth(
  fetcher: typeof fetch = fetch,
  baseUrl: string = DEFAULT_BASE_URL,
): Promise<HealthPayload> {
  const response = await fetcher(`${baseUrl}/api/health/`);

  if (!response.ok) {
    throw new Error('Backend health check failed');
  }

  return response.json() as Promise<HealthPayload>;
}
