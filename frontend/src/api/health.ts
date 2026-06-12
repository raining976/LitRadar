export interface HealthPayload {
  status: 'ok';
  service: string;
}

export async function fetchHealth(
  fetcher: typeof fetch = fetch,
  baseUrl = 'http://127.0.0.1:8765',
): Promise<HealthPayload> {
  const response = await fetcher(`${baseUrl}/api/health/`);

  if (!response.ok) {
    throw new Error('Backend health check failed');
  }

  return response.json() as Promise<HealthPayload>;
}
