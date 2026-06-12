import { describe, expect, it, vi } from 'vitest';
import { fetchHealth } from './health';

describe('fetchHealth', () => {
  it('returns backend health payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', service: 'litradar-backend' }),
    });

    const result = await fetchHealth(fetchMock, 'http://127.0.0.1:8765');

    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/health/');
    expect(result).toEqual({ status: 'ok', service: 'litradar-backend' });
  });
});
