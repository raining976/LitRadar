export interface LocalSettingsPayload {
  ai_base_url: string;
  ai_api_key?: string;
  has_ai_api_key?: boolean;
  text_model: string;
  vision_model: string;
  obsidian_vault_path: string;
}

export interface ResearchTopic {
  id: number;
  name: string;
  description: string;
  keywords: string[];
  arxiv_categories: string[];
  daily_limit: number;
  obsidian_folder: string;
  enabled: boolean;
}

export interface PaperInsight {
  research_direction?: string;
  task_definition?: string;
  module_list?: string;
  loss_functions?: string;
  training_process?: string;
  inference_process?: string;
  innovation_points?: string | string[];
  limitations?: string;
  reproduction_questions?: string;
  idea_hints?: string | string[];
  keywords?: string[];
  markdown_note?: string;
}

export interface PaperNote {
  content: string;
  source: string;
  target_relative_path: string;
  updated_at: string;
}

export interface Paper {
  id?: number;
  title: string;
  translated_title?: string;
  authors: string[];
  year: number | null;
  abstract: string;
  translated_abstract?: string;
  arxiv_id: string;
  source: string;
  source_url: string;
  pdf_url: string;
  google_scholar_url?: string;
  published_date?: string;
  version?: string;
  local_pdf_path?: string;
  topic: number | null;
  status?: string;
  tags?: string[];
  matched_terms?: string[];
  match_score?: number;
  figures?: unknown[];
  insight?: PaperInsight | null;
  note?: PaperNote | null;
}

export interface Recommendation {
  id: number;
  topic: ResearchTopic;
  paper: Paper;
  recommend_date: string;
  score: number;
  reason: string;
  idea_hint: string;
  exported_to_obsidian: boolean;
}

export interface RadarRunPayload {
  topic: ResearchTopic;
  date: string;
  recommendations: Recommendation[];
}

type Fetcher = typeof fetch;

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
const DEFAULT_BASE_URL = isTauri ? 'http://127.0.0.1:18765' : 'http://127.0.0.1:8765';

async function requestJson<T>(path: string, fetcher: Fetcher = fetch, baseUrl = DEFAULT_BASE_URL, init?: RequestInit): Promise<T> {
  const response = init === undefined ? await fetcher(`${baseUrl}${path}`) : await fetcher(`${baseUrl}${path}`, init);

  if (!response.ok) {
    let message = `LitRadar API request failed: ${path}`;
    try {
      const payload = await response.json() as { error?: string };
      message = payload.error || message;
    } catch {
      // keep generic message when backend returns a non-JSON error
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function jsonInit(method: 'POST' | 'PATCH', payload?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload ?? {}),
  };
}

export function fetchLocalSettings(fetcher?: Fetcher, baseUrl?: string): Promise<LocalSettingsPayload> {
  return requestJson('/api/settings/', fetcher, baseUrl);
}

export function saveLocalSettings(payload: Partial<LocalSettingsPayload>, fetcher?: Fetcher, baseUrl?: string): Promise<LocalSettingsPayload> {
  return requestJson('/api/settings/', fetcher, baseUrl, jsonInit('PATCH', payload));
}

export function fetchTopics(fetcher?: Fetcher, baseUrl?: string): Promise<ResearchTopic[]> {
  return requestJson('/api/topics/', fetcher, baseUrl);
}

export function createTopic(payload: Partial<ResearchTopic>, fetcher?: Fetcher, baseUrl?: string): Promise<ResearchTopic> {
  return requestJson('/api/topics/', fetcher, baseUrl, jsonInit('POST', payload));
}

export function updateTopic(id: number, payload: Partial<ResearchTopic>, fetcher?: Fetcher, baseUrl?: string): Promise<ResearchTopic> {
  return requestJson(`/api/topics/${id}/`, fetcher, baseUrl, jsonInit('PATCH', payload));
}

export function deleteTopic(id: number, fetcher?: Fetcher, baseUrl?: string): Promise<{ deleted: boolean }> {
  return requestJson(`/api/topics/${id}/`, fetcher, baseUrl, { method: 'DELETE' });
}

export function searchPapers(query: string, engine: string = 'arxiv', fromDate?: string, topicId?: number | null, fetcher?: Fetcher, baseUrl?: string): Promise<Paper[]> {
  const params = new URLSearchParams({ query, engine });
  if (fromDate) params.set('from_date', fromDate);
  if (topicId) params.set('topic_id', String(topicId));
  return requestJson(`/api/papers/search/?${params.toString()}`, fetcher, baseUrl);
}

export function fetchOpenAlexDiscovery(topicId: number, fetcher?: Fetcher, baseUrl?: string): Promise<Paper[]> {
  return requestJson(`/api/papers/openalex/discover/?topic_id=${topicId}`, fetcher, baseUrl);
}

export interface AiTestResult {
  ok: boolean;
  model?: string;
  error?: string;
}

export function translatePapersBatch(papers: Partial<Paper>[], fetcher?: Fetcher, baseUrl?: string): Promise<Paper[]> {
  return requestJson('/api/papers/translate-batch/', fetcher, baseUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ papers }),
  });
}

export function testAiConnection(fetcher?: Fetcher, baseUrl?: string): Promise<AiTestResult> {
  return requestJson('/api/settings/test-ai/', fetcher, baseUrl, { method: 'POST' });
}

export function fetchPapers(fetcher?: Fetcher, baseUrl?: string): Promise<Paper[]> {
  return requestJson('/api/papers/', fetcher, baseUrl);
}

export function createPaper(payload: Partial<Paper>, fetcher?: Fetcher, baseUrl?: string): Promise<Paper> {
  return requestJson('/api/papers/', fetcher, baseUrl, jsonInit('POST', payload));
}

export function updatePaper(id: number, payload: Partial<Paper>, fetcher?: Fetcher, baseUrl?: string): Promise<Paper> {
  return requestJson(`/api/papers/${id}/`, fetcher, baseUrl, jsonInit('PATCH', payload));
}

export function deletePaper(id: number, fetcher?: Fetcher, baseUrl?: string): Promise<{ deleted: boolean }> {
  return requestJson(`/api/papers/${id}/`, fetcher, baseUrl, { method: 'DELETE' });
}

export function runRadar(topicId: number, limit: number, fetcher?: Fetcher, baseUrl?: string): Promise<RadarRunPayload> {
  return requestJson(`/api/radar/run/${topicId}/`, fetcher, baseUrl, jsonInit('POST', { limit }));
}

export function fetchTodayRadar(fetcher?: Fetcher, baseUrl?: string): Promise<Recommendation[]> {
  return requestJson('/api/radar/today/', fetcher, baseUrl);
}

export function analyzePaperStructure(paperId: number, fetcher?: Fetcher, baseUrl?: string): Promise<PaperInsight> {
  return requestJson(`/api/papers/${paperId}/analyze-structure/`, fetcher, baseUrl, { method: 'POST' });
}

export function fetchPaperNote(paperId: number, fetcher?: Fetcher, baseUrl?: string): Promise<PaperNote> {
  return requestJson(`/api/papers/${paperId}/note/`, fetcher, baseUrl);
}

export function generatePaperNote(paperId: number, force = false, fetcher?: Fetcher, baseUrl?: string): Promise<PaperNote> {
  return requestJson(`/api/papers/${paperId}/note/`, fetcher, baseUrl, jsonInit('POST', { force }));
}
