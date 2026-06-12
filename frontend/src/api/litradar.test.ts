import { describe, expect, it, vi } from 'vitest';
import {
  deletePaper,
  deleteTopic,
  analyzePaperStructure,
  createPaper,
  createTopic,
  fetchLocalSettings,
  fetchPapers,
  fetchPaperMarkdown,
  fetchTopics,
  runRadar,
  saveLocalSettings,
  searchPapers,
  updatePaper,
  updateTopic,
} from './litradar';

function jsonResponse(payload: unknown, ok = true) {
  return {
    ok,
    json: async () => payload,
  } as Response;
}

describe('LitRadar API client', () => {
  it('fetches and saves local settings without exposing api key in responses', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ has_ai_api_key: false, ai_base_url: '', text_model: '', vision_model: '', obsidian_vault_path: '' }))
      .mockResolvedValueOnce(jsonResponse({ has_ai_api_key: true, ai_base_url: 'https://relay.example/v1', text_model: 'claude', vision_model: '', obsidian_vault_path: '/vault' }));

    const settings = await fetchLocalSettings(fetcher, 'http://127.0.0.1:8765');
    const saved = await saveLocalSettings({ ai_base_url: 'https://relay.example/v1', ai_api_key: 'secret', obsidian_vault_path: '/vault' }, fetcher, 'http://127.0.0.1:8765');

    expect(settings.has_ai_api_key).toBe(false);
    expect(saved.has_ai_api_key).toBe(true);
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/settings/', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ai_base_url: 'https://relay.example/v1', ai_api_key: 'secret', obsidian_vault_path: '/vault' }),
    });
  });

  it('creates, lists, updates, and deletes topics', async () => {
    const topic = { id: 1, name: '遥感变化检测', keywords: ['change detection'], arxiv_categories: [], daily_limit: 3, obsidian_folder: '', enabled: true, description: '' };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(topic));

    await createTopic({ name: topic.name, keywords: topic.keywords }, fetcher, 'http://127.0.0.1:8765');
    await updateTopic(1, { daily_limit: 2 }, fetcher, 'http://127.0.0.1:8765');
    await deleteTopic(1, fetcher, 'http://127.0.0.1:8765');

    expect(fetcher).toHaveBeenNthCalledWith(1, 'http://127.0.0.1:8765/api/topics/', expect.objectContaining({ method: 'POST' }));
    expect(fetcher).toHaveBeenNthCalledWith(2, 'http://127.0.0.1:8765/api/topics/1/', expect.objectContaining({ method: 'PATCH' }));
    expect(fetcher).toHaveBeenNthCalledWith(3, 'http://127.0.0.1:8765/api/topics/1/', { method: 'DELETE' });

    fetcher.mockResolvedValueOnce(jsonResponse([topic]));
    await expect(fetchTopics(fetcher, 'http://127.0.0.1:8765')).resolves.toEqual([topic]);
  });

  it('searches, saves, analyzes, and previews papers', async () => {
    const paper = { id: 1, title: 'Change Detection with Transformers', authors: ['A'], year: 2026, abstract: '', arxiv_id: '2601.1', source: 'arXiv', source_url: '', pdf_url: '', topic: 1, status: 'saved', figures: [], insight: null };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse([paper]));

    await expect(searchPapers('change detection', 1, fetcher, 'http://127.0.0.1:8765')).resolves.toEqual([paper]);
    expect(fetcher).toHaveBeenCalledWith('http://127.0.0.1:8765/api/papers/search/?query=change+detection&topic_id=1');

    fetcher.mockResolvedValueOnce(jsonResponse(paper));
    await createPaper(paper, fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/', expect.objectContaining({ method: 'POST' }));

    fetcher.mockResolvedValueOnce(jsonResponse({ ...paper, title: 'Updated' }));
    await updatePaper(1, { title: 'Updated' }, fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/1/', expect.objectContaining({ method: 'PATCH' }));

    fetcher.mockResolvedValueOnce(jsonResponse({ deleted: true }));
    await deletePaper(1, fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/1/', { method: 'DELETE' });

    fetcher.mockResolvedValueOnce(jsonResponse({ research_direction: '变化检测' }));
    await analyzePaperStructure(1, fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/1/analyze-structure/', { method: 'POST' });

    fetcher.mockResolvedValueOnce(jsonResponse({ target_relative_path: 'Papers/a.md', markdown: '# A' }));
    await fetchPaperMarkdown(1, fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/1/obsidian-markdown/');

    fetcher.mockResolvedValueOnce(jsonResponse([paper]));
    await fetchPapers(fetcher, 'http://127.0.0.1:8765');
    expect(fetcher).toHaveBeenLastCalledWith('http://127.0.0.1:8765/api/papers/');
  });

  it('surfaces backend error payload messages', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ error: 'arXiv 暂时不可用，请稍后再试。' }, false));

    await expect(searchPapers('remote sensing', null, fetcher, 'http://127.0.0.1:8765')).rejects.toThrow('arXiv 暂时不可用，请稍后再试。');
  });

  it('runs daily radar for a topic', async () => {
    const payload = { topic: { id: 1, name: '变化检测' }, date: '2026-05-26', recommendations: [] };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(payload));

    await expect(runRadar(1, 2, fetcher, 'http://127.0.0.1:8765')).resolves.toEqual(payload);
    expect(fetcher).toHaveBeenCalledWith('http://127.0.0.1:8765/api/radar/run/1/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit: 2 }),
    });
  });
});
