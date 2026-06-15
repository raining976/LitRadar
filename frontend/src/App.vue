<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchHealth, type HealthPayload } from './api/health';
import {
  analyzePaperStructure,
  createPaper,
  createTopic,
  deletePaper,
  fetchLocalSettings,
  fetchOpenAlexDiscovery,
  fetchPaperNote,
  fetchPapers,
  fetchTodayRadar,
  fetchTopics,
  generatePaperNote,
  runRadar,
  saveLocalSettings,
  searchPapers,
  updatePaper,
  updateTopic,
  type LocalSettingsPayload,
  type Paper,
  type PaperNote,
  type Recommendation,
  type ResearchTopic,
} from './api/litradar';

type Workspace = 'radar' | 'library' | 'search' | 'settings';
type NotificationTone = 'info' | 'success' | 'warning' | 'error';
type ReaderMode = 'summary' | 'pdf' | 'graph' | 'note';

interface NotificationItem {
  id: number;
  tone: NotificationTone;
  message: string;
}

interface NavItem {
  id: Workspace;
  label: string;
  description: string;
  icon: 'radar' | 'library' | 'search' | 'settings';
}

const navItems: NavItem[] = [
  { id: 'radar', label: '今日雷达', description: '每日推荐', icon: 'radar' },
  { id: 'library', label: '论文库', description: '知识库工作台', icon: 'library' },
  { id: 'search', label: '论文搜索', description: 'arXiv 检索', icon: 'search' },
  { id: 'settings', label: '本地设置', description: '本地服务', icon: 'settings' },
];

const health = ref<HealthPayload | null>(null);
const activeTab = ref<Workspace>('radar');
const sidebarExpanded = ref(false);
const loadingAction = ref<string | null>(null);
const notification = ref<NotificationItem | null>(null);
const notificationTimer = ref<ReturnType<typeof setTimeout> | null>(null);
const topics = ref<ResearchTopic[]>([]);
const papers = ref<Paper[]>([]);
const recommendations = ref<Recommendation[]>([]);
const searchResults = ref<Paper[]>([]);
const discoverResults = ref<Paper[]>([]);
const discoverLoading = ref(false);
const discoverTopicId = ref<number | null>(null);
const selectedTopicId = ref<number | null>(null);
const selectedPaperId = ref<number | null>(null);
const editingPaperId = ref<number | null>(null);
const readerMode = ref<ReaderMode>('summary');
const radarLimit = ref(3);
const radarLimitEditing = ref(false);
const radarLimitDraft = ref(3);
const paperNote = ref<PaperNote | null>(null);
const notificationId = ref(0);
const settings = ref<LocalSettingsPayload>({
  ai_base_url: '',
  ai_api_key: '',
  text_model: '',
  vision_model: '',
  obsidian_vault_path: '',
});

const topicForm = ref({
  name: '遥感变化检测',
  keywordsText: 'remote sensing change detection\nSAR change detection',
});

const paperForm = ref({
  title: '',
  status: 'saved',
  local_pdf_path: '',
});

const searchForm = ref({
  query: 'remote sensing change detection',
});

const selectedPaper = computed(() => papers.value.find((paper) => paper.id === selectedPaperId.value) ?? null);
const savedPaperKeys = computed(() => new Set(papers.value.flatMap((paper) => [
  paper.arxiv_id ? `arxiv:${paper.arxiv_id}` : '',
  paper.title ? `title:${paper.title.toLowerCase()}` : '',
]).filter(Boolean)));
const activeTopic = computed(() => topics.value.find((topic) => topic.id === selectedTopicId.value) ?? null);

function discoverCacheKey(topicId: number): string {
  return `litradar_discover_${topicId}`;
}

function loadDiscoverCache(topicId: number): Paper[] | null {
  try {
    const raw = localStorage.getItem(discoverCacheKey(topicId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as Paper[];
    return null;
  } catch { return null; }
}

function saveDiscoverCache(topicId: number, papers: Paper[]): void {
  try { localStorage.setItem(discoverCacheKey(topicId), JSON.stringify(papers)); } catch { /* quota exceeded */ }
}

async function loadOpenAlexDiscovery(topicId: number, forceRefresh = false) {
  if (!forceRefresh) {
    const cached = loadDiscoverCache(topicId);
    if (cached && cached.length > 0) {
      discoverResults.value = cached;
      discoverTopicId.value = topicId;
      return;
    }
  }
  discoverLoading.value = true;
  try {
    const papers = await fetchOpenAlexDiscovery(topicId);
    discoverResults.value = papers;
    discoverTopicId.value = topicId;
    saveDiscoverCache(topicId, papers);
  } catch (caught) {
    pushNotification(caught instanceof Error ? caught.message : 'OpenAlex 发现加载失败', 'warning');
    const stale = loadDiscoverCache(topicId);
    if (stale && stale.length > 0) {
      discoverResults.value = stale;
      discoverTopicId.value = topicId;
    }
  } finally {
    discoverLoading.value = false;
  }
}

async function refreshOpenAlexDiscovery() {
  if (discoverTopicId.value != null) {
    await loadOpenAlexDiscovery(discoverTopicId.value, true);
    pushNotification('OpenAlex 发现已刷新。', 'success');
  }
}

const hasApiKey = computed(() => Boolean(settings.value.has_ai_api_key || settings.value.ai_api_key));
const hasObsidian = computed(() => Boolean(settings.value.obsidian_vault_path));
const statusCards = computed(() => [
  { label: '本地后端', value: health.value ? '已连接' : '未连接', tone: health.value ? 'success' : 'error' },
  { label: '雷达方向', value: activeTopic.value?.name ?? '未配置', tone: activeTopic.value ? 'success' : 'warning' },
  { label: 'AI 中转站', value: hasApiKey.value ? 'Key 已配置' : '未配置', tone: hasApiKey.value ? 'success' : 'warning' },
  { label: 'Obsidian', value: hasObsidian.value ? '已配置' : '仅预览', tone: hasObsidian.value ? 'success' : 'warning' },
]);
const workspaceTitle = computed(() => navItems.find((item) => item.id === activeTab.value)?.label ?? '工作台');
const workspaceSubtitle = computed(() => navItems.find((item) => item.id === activeTab.value)?.description ?? 'LitRadar');
const isPaperDetail = computed(() => activeTab.value === 'library' && Boolean(selectedPaper.value));

function lines(text: string): string[] {
  return text
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isLoading(action: string) {
  return loadingAction.value === action;
}

function pushNotification(message: string, tone: NotificationTone = 'info') {
  notification.value = { id: notificationId.value++, message, tone };
  if (notificationTimer.value) {
    clearTimeout(notificationTimer.value);
  }
  notificationTimer.value = setTimeout(() => {
    notification.value = null;
  }, 3200);
}

function formatAuthors(authors: string[]): string {
  if (!authors.length) return '未知作者';
  return authors.slice(0, 3).join(', ') + (authors.length > 3 ? ' 等' : '');
}

function scholarUrl(paper: Paper): string {
  return paper.google_scholar_url || `https://scholar.google.com/scholar?q=${encodeURIComponent(paper.title)}`;
}

function displayTitleZh(paper: Paper): string {
  return paper.translated_title?.trim() || paper.title;
}

function displayAbstractZh(paper: Paper): string {
  return paper.translated_abstract?.trim() || paper.abstract || '添加到论文库并完成 AI 结构化阅读后，会优先展示中文摘要。';
}

function displayDate(paper: Paper): string {
  return paper.published_date || (paper.year ? String(paper.year) : '未知时间');
}

function displayVersion(paper: Paper): string {
  return paper.version || (paper.arxiv_id.match(/v\d+$/)?.[0] ?? '未知版本');
}

function paperKey(paper: Paper): string {
  return paper.arxiv_id ? `arxiv:${paper.arxiv_id}` : `title:${paper.title.toLowerCase()}`;
}

function isPaperSaved(paper: Paper): boolean {
  return savedPaperKeys.value.has(paperKey(paper));
}

function setActiveTab(tab: Workspace) {
  activeTab.value = tab;
  if (tab === 'library') {
    selectedPaperId.value = null;
    editingPaperId.value = null;
  }
  if (tab === 'search' && searchResults.value.length === 0) {
    const topicId = activeTopic.value?.id ?? topics.value[0]?.id;
    if (topicId != null && (discoverTopicId.value !== topicId || discoverResults.value.length === 0)) {
      loadOpenAlexDiscovery(topicId);
    }
  }
}

function showLibraryList() {
  selectedPaperId.value = null;
  editingPaperId.value = null;
  paperNote.value = null;
  readerMode.value = 'summary';
}

function selectPaper(paperId?: number | null) {
  selectedPaperId.value = paperId ?? null;
  paperNote.value = null;
  readerMode.value = 'summary';
  editingPaperId.value = null;
  activeTab.value = 'library';
}

function editPaper(paper: Paper) {
  paperForm.value = {
    title: paper.title,
    status: paper.status || 'saved',
    local_pdf_path: paper.local_pdf_path || '',
  };
  selectPaper(paper.id);
  editingPaperId.value = paper.id ?? null;
}

function saveRadarLimit() {
  radarLimit.value = Math.max(1, Math.min(Number(radarLimitDraft.value) || 3, 10));
  radarLimitEditing.value = false;
}

function startRadarLimitEdit() {
  radarLimitDraft.value = radarLimit.value;
  radarLimitEditing.value = true;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightedParts(text: string, terms: string[] = []) {
  const usableTerms = terms.filter((term) => term.trim().length > 1).slice(0, 12);
  if (!usableTerms.length) return [{ text, match: false }];
  const pattern = new RegExp(`(${usableTerms.map(escapeRegExp).join('|')})`, 'ig');
  return text.split(pattern).filter(Boolean).map((part) => ({
    text: part,
    match: usableTerms.some((term) => term.toLowerCase() === part.toLowerCase()),
  }));
}

function noteList(value?: string | string[]): string[] {
  if (Array.isArray(value)) return value.filter((item) => item.trim().length > 0);
  if (!value?.trim()) return [];
  const trimmed = value.trim();
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    return trimmed
      .replace(/^\[|\]$/g, '')
      .split(/',\s*'|",\s*"/)
      .map((item) => item.replace(/^['"]|['"]$/g, '').trim())
      .filter(Boolean);
  }
  return trimmed.split('\n').map((item) => item.replace(/^-\s*/, '').trim()).filter(Boolean);
}

function noteText(value?: string | string[]): string {
  if (Array.isArray(value)) return value.join('；');
  return value || '待分析。';
}

type NoteBlock = { type: 'heading' | 'paragraph' | 'list'; level?: number; text?: string; items?: string[] };

function noteBlocks(markdown?: string): NoteBlock[] {
  if (!markdown?.trim()) return [];
  const blocks: NoteBlock[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      blocks.push({ type: 'list', items: [...listItems] });
      listItems = [];
    }
  };
  markdown.split('\n').forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line || line === '---') {
      flushParagraph();
      flushList();
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      return;
    }
    const list = line.match(/^[-*]\s+(.+)$/);
    if (list) {
      flushParagraph();
      listItems.push(list[1]);
      return;
    }
    flushList();
    paragraph.push(line);
  });
  flushParagraph();
  flushList();
  return blocks;
}

async function withLoading(actionName: string, action: () => Promise<void>) {
  loadingAction.value = actionName;
  try {
    await action();
  } catch (caught) {
    pushNotification(caught instanceof Error ? caught.message : '操作失败', 'error');
  } finally {
    loadingAction.value = null;
  }
}

async function refreshCollections() {
  const [topicsPayload, papersPayload, radarPayload] = await Promise.all([
    fetchTopics(),
    fetchPapers(),
    fetchTodayRadar(),
  ]);
  topics.value = topicsPayload;
  papers.value = papersPayload;
  if (!selectedTopicId.value || !topicsPayload.some((topic) => topic.id === selectedTopicId.value)) {
    selectedTopicId.value = topicsPayload[0]?.id ?? null;
  }
  recommendations.value = selectedTopicId.value
    ? radarPayload.filter((item) => item.topic.id === selectedTopicId.value)
    : radarPayload;
  const topic = topicsPayload.find((item) => item.id === selectedTopicId.value) ?? topicsPayload[0];
  if (topic) {
    topicForm.value = {
      name: topic.name,
      keywordsText: topic.keywords.join('\n'),
    };
  }
  if (selectedPaperId.value && !papersPayload.some((paper) => paper.id === selectedPaperId.value)) {
    selectedPaperId.value = null;
  }
}

async function loadAll() {
  await withLoading('load', async () => {
    health.value = await fetchHealth();
    const settingsPayload = await fetchLocalSettings();
    settings.value = { ...settings.value, ...settingsPayload, ai_api_key: '' };
    await refreshCollections();
    if (!settingsPayload.obsidian_vault_path) {
      pushNotification('Obsidian 未配置：当前只生成 Markdown 预览，不写入本地知识库。', 'warning');
    }
    const topicId = selectedTopicId.value ?? topics.value[0]?.id;
    if (topicId != null) {
      loadOpenAlexDiscovery(topicId);
    }
  });
}

async function submitSettings() {
  await withLoading('settings', async () => {
    const payload = { ...settings.value };
    if (!payload.ai_api_key) {
      delete payload.ai_api_key;
    }
    settings.value = { ...await saveLocalSettings(payload), ai_api_key: '' };
    pushNotification('本地设置已保存。', 'success');
  });
}

async function saveRadarTopic(notify = true) {
  const payload = {
    name: topicForm.value.name.trim() || '我的研究方向',
    description: '',
    keywords: lines(topicForm.value.keywordsText),
    arxiv_categories: [],
    obsidian_folder: '',
    enabled: true,
  };
  const topic = activeTopic.value
    ? await updateTopic(activeTopic.value.id, payload)
    : await createTopic({ ...payload, daily_limit: 3 });
  selectedTopicId.value = topic.id;
  await refreshCollections();
  if (notify) {
    pushNotification('今日雷达研究方向已保存。', 'success');
  }
  return topic;
}

async function submitRadarTopic() {
  await withLoading('topic-save', async () => {
    await saveRadarTopic();
  });
}

async function submitSearch() {
  await withLoading('search', async () => {
    searchResults.value = await searchPapers(searchForm.value.query);
    pushNotification(`找到 ${searchResults.value.length} 篇候选论文。`, 'success');
  });
}

async function savePaper(paper: Paper) {
  await withLoading(`save-paper-${paper.arxiv_id || paper.title}`, async () => {
    const saved = await createPaper({ ...paper, topic: null, status: 'saved' });
    await analyzePaperStructure(saved.id as number);
    await refreshCollections();
    selectPaper(saved.id);
    readerMode.value = 'summary';
    pushNotification('论文已添加到论文库，并已触发 AI 结构化阅读。', 'success');
  });
}

async function saveRecommendation(item: Recommendation) {
  await withLoading(`save-paper-${item.paper.arxiv_id || item.paper.title}`, async () => {
    const saved = await createPaper({ ...item.paper, topic: item.topic.id, status: 'saved' });
    await analyzePaperStructure(saved.id as number);
    await refreshCollections();
    selectPaper(saved.id);
    readerMode.value = 'summary';
    pushNotification('推荐论文已添加到论文库，并已触发 AI 结构化阅读。', 'success');
  });
}

async function submitPaperEdit() {
  if (!editingPaperId.value) return;
  await withLoading('paper-save', async () => {
    await updatePaper(editingPaperId.value as number, {
      title: paperForm.value.title,
      status: paperForm.value.status,
      local_pdf_path: paperForm.value.local_pdf_path,
    });
    await refreshCollections();
    editingPaperId.value = null;
    pushNotification('论文信息已更新。', 'success');
  });
}

async function removePaper(paper: Paper) {
  if (!paper.id || !window.confirm(`确认从论文库删除「${paper.title}」？`)) return;
  await withLoading(`paper-delete-${paper.id}`, async () => {
    await deletePaper(paper.id as number);
    await refreshCollections();
    pushNotification('论文已删除。', 'success');
  });
}

async function submitRadar() {
  if (!topicForm.value.name.trim() && !topicForm.value.keywordsText.trim()) {
    pushNotification('请先填写今日雷达的研究方向。', 'warning');
    return;
  }
  await withLoading('radar', async () => {
    const topic = await saveRadarTopic(false);
    const payload = await runRadar(topic.id, radarLimit.value);
    await refreshCollections();
    pushNotification(`${payload.topic.name} 今日雷达生成 ${payload.recommendations.length} 篇推荐。`, 'success');
  });
}

async function analyzeSelectedPaper() {
  if (!selectedPaperId.value) return;
  await withLoading('analyze', async () => {
    await analyzePaperStructure(selectedPaperId.value as number);
    await refreshCollections();
    readerMode.value = 'summary';
    pushNotification('结构化阅读笔记已生成。', 'success');
  });
}

async function generateSelectedPaperNote(force = false) {
  if (!selectedPaperId.value) return;
  await withLoading('paper-note', async () => {
    paperNote.value = await generatePaperNote(selectedPaperId.value as number, force);
    await refreshCollections();
    readerMode.value = 'note';
    pushNotification('论文深度笔记已生成并同步到 Obsidian。', 'success');
  });
}

async function loadSelectedPaperNote() {
  if (!selectedPaperId.value) return;
  await withLoading('paper-note-load', async () => {
    paperNote.value = await fetchPaperNote(selectedPaperId.value as number);
    readerMode.value = 'note';
  });
}

onMounted(loadAll);
</script>

<template>
  <main class="desktop-shell">
    <aside class="sidebar" :class="{ expanded: sidebarExpanded }">
      <div class="brand-block">
        <span class="brand-mark">LR</span>
        <div class="brand-copy">
          <strong>LitRadar</strong>
          <small>个人文献雷达</small>
        </div>
        <button class="sidebar-toggle" type="button" :aria-label="sidebarExpanded ? '收起导航' : '展开导航'" @click="sidebarExpanded = !sidebarExpanded">
          <span />
        </button>
      </div>

      <nav class="side-nav">
        <button v-for="item in navItems" :key="item.id" :class="{ active: activeTab === item.id }" :title="item.label" @click="setActiveTab(item.id)">
          <span class="nav-icon" :class="item.icon" aria-hidden="true" />
          <span class="nav-copy">
            <span>{{ item.label }}</span>
            <small>{{ item.description }}</small>
          </span>
        </button>
      </nav>
    </aside>

    <section class="workspace">
      <header class="topbar" :class="{ 'detail-topbar': isPaperDetail }">
        <div v-if="!isPaperDetail" class="topbar-title">
          <div class="topbar-heading">
            <p class="eyebrow">{{ workspaceSubtitle }}</p>
            <h1>{{ workspaceTitle }}</h1>
          </div>
          <div v-if="activeTab === 'radar'" class="topbar-radar-controls">
            <div class="radar-limit-row">
              <span>每日推荐数量</span>
              <strong v-if="!radarLimitEditing">{{ radarLimit }}</strong>
              <input v-else v-model.number="radarLimitDraft" type="number" min="1" max="10" />
              <button v-if="!radarLimitEditing" class="ghost" @click="startRadarLimitEdit">编辑</button>
              <button v-else class="primary" @click="saveRadarLimit">保存</button>
            </div>
            <button class="primary" :disabled="isLoading('radar')" @click="submitRadar">
              <span v-if="isLoading('radar')" class="spinner"></span>{{ isLoading('radar') ? '更新中' : '更新今日推荐' }}
            </button>
          </div>
          <span v-if="activeTab === 'library'" class="topbar-badge">{{ papers.length }} 篇</span>
          <span v-if="activeTab === 'search' && searchResults.length" class="topbar-badge">共找到 {{ searchResults.length }} 篇</span>
        </div>
        <div v-else-if="selectedPaper" class="library-breadcrumb detail-breadcrumb">
          <button class="ghost" @click="showLibraryList">论文列表</button>
          <span>/</span>
          <strong>{{ selectedPaper.title.length > 36 ? '论文详情' : displayTitleZh(selectedPaper) }}</strong>
        </div>
        <nav v-if="isPaperDetail" class="reader-tabs detail-tabs" aria-label="论文详情导航">
          <button :class="{ active: readerMode === 'summary' }" @click="readerMode = 'summary'">摘要</button>
          <button :class="{ active: readerMode === 'pdf' }" @click="readerMode = 'pdf'">PDF</button>
          <button :class="{ active: readerMode === 'graph' }" @click="readerMode = 'graph'">知识图谱</button>
          <button :class="{ active: readerMode === 'note' }" @click="loadSelectedPaperNote">论文笔记</button>
        </nav>
        <div class="topbar-action">
          <span v-if="loadingAction" class="status-pill info"><i class="spinner"></i> 处理中</span>
        </div>
      </header>

      <article v-if="notification" class="toast" :class="notification.tone">
        {{ notification.message }}
      </article>

      <section v-if="activeTab === 'radar'" class="page-grid radar-page">
        <div class="content-panel wide-panel">
          <div v-if="recommendations.length" class="recommendation-list">
            <article v-for="item in recommendations" :key="item.id" class="recommendation-card">
              <div>
                <span class="score">{{ item.score }}</span>
                <small>{{ item.topic.name }}</small>
              </div>
              <section>
                <div class="recommendation-title-row">
                  <div>
                    <h3>{{ displayTitleZh(item.paper) }}</h3>
                    <div class="result-meta">
                      <span>{{ displayDate(item.paper) }}</span>
                      <span>{{ item.paper.source || 'arXiv' }}</span>
                    </div>
                  </div>
                  <button class="secondary" :disabled="isLoading(`save-paper-${item.paper.arxiv_id || item.paper.title}`)" @click="saveRecommendation(item)">
                    <span v-if="isLoading(`save-paper-${item.paper.arxiv_id || item.paper.title}`)" class="spinner"></span>添加到论文库
                  </button>
                </div>
                <p class="recommendation-summary">{{ displayAbstractZh(item.paper) }}</p>
              </section>
            </article>
          </div>
          <div v-else class="empty-state">还没有今日推荐。填写右侧研究方向并设置数量后，点击更新今日推荐。</div>
        </div>

        <aside class="content-panel topic-side-panel form-panel">
          <label>名称<input v-model="topicForm.name" placeholder="例如 遥感变化检测" /></label>
          <label>关键词（每行一个）<textarea v-model="topicForm.keywordsText" placeholder="remote sensing change detection&#10;SAR change detection" /></label>
          <button class="primary" :disabled="isLoading('topic-save')" @click="submitRadarTopic">
            <span v-if="isLoading('topic-save')" class="spinner"></span>保存方向
          </button>
        </aside>
      </section>

      <section v-if="activeTab === 'library'" class="library-workbench">
        <section v-if="!selectedPaper" class="content-panel library-list-page">
          <div v-if="papers.length" class="search-result-grid library-card-grid">
            <article v-for="paper in papers" :key="paper.id" class="search-result-card library-paper-card" @click="selectPaper(paper.id)">
              <div class="result-card-actions">
                <button class="icon-button saved" title="已在论文库">★</button>
                <button class="icon-button" title="编辑信息" @click.stop="editPaper(paper)">✎</button>
              </div>
              <h3>{{ displayTitleZh(paper) }}</h3>
              <div class="result-meta">
                <span>{{ displayDate(paper) }}</span>
                <span>{{ paper.source || 'arXiv' }}</span>
              </div>
              <p>{{ displayAbstractZh(paper) }}</p>
            </article>
          </div>
          <div v-else class="empty-state">还没有保存论文。先从论文搜索或今日雷达保存候选论文。</div>
        </section>

        <section class="reader-pane paper-detail" v-if="selectedPaper">
          <form v-if="editingPaperId" class="edit-strip" @submit.prevent="submitPaperEdit">
            <label>标题<input v-model="paperForm.title" /></label>
            <label>状态<input v-model="paperForm.status" /></label>
            <label>本地 PDF<input v-model="paperForm.local_pdf_path" /></label>
            <div class="button-row">
              <button class="primary" type="submit" :disabled="isLoading('paper-save')">保存论文</button>
              <button class="ghost" type="button" @click="editingPaperId = null">取消</button>
            </div>
          </form>

          <template v-if="readerMode === 'summary'">
            <article class="summary-hero content-panel">
              <div class="paper-cover">
                <span>{{ selectedPaper.source || 'arXiv' }}</span>
                <strong>{{ selectedPaper.arxiv_id || 'paper' }}</strong>
              </div>
              <section class="paper-meta">
                <h2>{{ displayTitleZh(selectedPaper) }}</h2>
                <h3>{{ selectedPaper.title }}</h3>
                <div class="author-row">
                  <span v-for="author in selectedPaper.authors" :key="author">{{ author }}</span>
                  <span v-if="!selectedPaper.authors.length">未知作者</span>
                </div>
                <div class="link-row">
                  <a :href="scholarUrl(selectedPaper)" target="_blank" rel="noreferrer">Google Scholar</a>
                  <a v-if="selectedPaper.source_url" :href="selectedPaper.source_url" target="_blank" rel="noreferrer">Arxiv 页面</a>
                  <a v-if="selectedPaper.pdf_url" :href="selectedPaper.pdf_url" target="_blank" rel="noreferrer">PDF</a>
                </div>
                <div class="meta-row">
                  <span>{{ selectedPaper.source || 'arXiv' }}</span>
                  <span>发表：{{ displayDate(selectedPaper) }}</span>
                  <span>版本 {{ displayVersion(selectedPaper) }}</span>
                </div>
                <div class="button-row">
                  <button class="secondary" :disabled="isLoading('analyze')" @click="analyzeSelectedPaper">
                    <span v-if="isLoading('analyze')" class="spinner"></span>刷新 AI 摘要
                  </button>
                  <button class="ghost" @click="editPaper(selectedPaper)">编辑信息</button>
                </div>
              </section>
            </article>

            <article class="abstract-card content-panel">
              <h2>中文摘要</h2>
              <p>{{ displayAbstractZh(selectedPaper) }}</p>
              <h2>英文摘要</h2>
              <p>{{ selectedPaper.abstract || '暂无英文摘要。' }}</p>
            </article>
          </template>

          <article v-if="readerMode === 'pdf'" class="pdf-render-panel content-panel">
            <div v-if="!selectedPaper.pdf_url" class="empty-state">{{ selectedPaper.local_pdf_path || '暂无 PDF 地址。' }}</div>
            <iframe v-else :src="selectedPaper.pdf_url" class="pdf-embed-frame" title="PDF 预览" />
          </article>

          <article v-if="readerMode === 'graph'" class="insight-panel content-panel single-reader">
            <template v-if="selectedPaper.insight">
              <section class="note-section">
                <span class="note-label">主题节点</span>
                <p>{{ selectedPaper.insight.research_direction || '未分类方向' }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">核心关系</span>
                <p>{{ selectedPaper.insight.task_definition || '待分析。' }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">创新点节点</span>
                <ul v-if="noteList(selectedPaper.insight.innovation_points).length" class="note-list">
                  <li v-for="item in noteList(selectedPaper.insight.innovation_points)" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ noteText(selectedPaper.insight.innovation_points) }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">Obsidian 可连接 idea</span>
                <ul v-if="noteList(selectedPaper.insight.idea_hints).length" class="note-list">
                  <li v-for="item in noteList(selectedPaper.insight.idea_hints)" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ noteText(selectedPaper.insight.idea_hints) }}</p>
              </section>
            </template>
            <p v-else class=”empty-state”>还没有结构化阅读结果。点击”刷新 AI 摘要”生成知识图谱素材。</p>
          </article>

          <article v-if="readerMode === 'note'" class="paper-note-panel content-panel single-reader">
            <div class="panel-heading compact-heading controls-only">
              <div class="button-row">
                <button class="secondary" :disabled="isLoading('paper-note')" @click="generateSelectedPaperNote(false)">
                  <span v-if="isLoading('paper-note')" class="spinner"></span>生成笔记
                </button>
                <button class="ghost" :disabled="isLoading('paper-note')" @click="generateSelectedPaperNote(true)">重新生成</button>
              </div>
            </div>
            <div v-if="paperNote?.content && paperNote?.target_relative_path" class="markdown-target">{{ paperNote.target_relative_path }}</div>
            <div v-if="paperNote?.content" class="note-rendered">
              <template v-for="(block, index) in noteBlocks(paperNote.content)" :key="index">
                <h2 v-if="block.type === 'heading'" :class="`note-heading level-${block.level}`">{{ block.text }}</h2>
                <ul v-else-if="block.type === 'list'" class="note-render-list">
                  <li v-for="item in block.items" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ block.text }}</p>
              </template>
            </div>
            <p v-else class="empty-state">还没有深度论文笔记。点击“生成笔记”后会用 paper-qa 优先阅读 PDF，并同步到 Obsidian。</p>
          </article>
        </section>

      </section>

      <section v-if="activeTab === 'search'" class="content-panel search-panel">
        <div class="search-bar">
          <input v-model="searchForm.query" placeholder="用分号分隔关键词，例如 HSI；classify" />
          <button class="primary" :disabled="isLoading('search')" @click="submitSearch">
            <span v-if="isLoading('search')" class="spinner"></span>{{ isLoading('search') ? '搜索中' : '搜索' }}
          </button>
        </div>

        <template v-if="searchResults.length">
          <div class="search-result-grid">
            <article v-for="(paper, index) in searchResults" :key="paper.arxiv_id || paper.title" class="search-result-card">
              <div class="result-card-actions">
                <button class="icon-button" :class="{ saved: isPaperSaved(paper) }" :disabled="isPaperSaved(paper) || isLoading(`save-paper-${paper.arxiv_id || paper.title}`)" :title="isPaperSaved(paper) ? '已在论文库' : '添加到论文库'" @click="savePaper(paper)">{{ isPaperSaved(paper) ? '★' : '☆' }}</button>
                <a class="icon-button" :href="scholarUrl(paper)" target="_blank" rel="noreferrer" title="Google Scholar">↗</a>
              </div>
              <h3><span class="result-index">{{ index + 1 }}.</span> {{ displayTitleZh(paper) }}</h3>
              <div class="result-meta">
                <span>{{ displayDate(paper) }}</span>
                <span>{{ paper.source || 'arXiv' }}</span>
                <span v-if="paper.match_score !== undefined" class="score-badge">🔥 {{ paper.match_score }}</span>
              </div>
              <p>{{ displayAbstractZh(paper) }}</p>
            </article>
          </div>
        </template>

        <template v-else>
          <div class="discovery-header">
            <span class="discovery-title">来自 OpenAlex 的 {{ activeTopic?.name || '研究方向' }} 推荐</span>
            <button class="ghost" :disabled="discoverLoading" @click="refreshOpenAlexDiscovery" title="刷新推荐">
              <span v-if="discoverLoading" class="spinner"></span>
              {{ discoverLoading ? '加载中' : '↻ 刷新' }}
            </button>
          </div>
          <div v-if="discoverResults.length" class="search-result-grid">
            <article v-for="(paper, index) in discoverResults" :key="(paper as any).openalex_id || paper.title" class="search-result-card">
              <div class="result-card-actions">
                <button class="icon-button" :class="{ saved: isPaperSaved(paper) }" :disabled="isPaperSaved(paper) || isLoading(`save-paper-${paper.arxiv_id || paper.title}`)" :title="isPaperSaved(paper) ? '已在论文库' : '添加到论文库'" @click="savePaper(paper)">{{ isPaperSaved(paper) ? '★' : '☆' }}</button>
                <a class="icon-button" :href="scholarUrl(paper)" target="_blank" rel="noreferrer" title="Google Scholar">↗</a>
              </div>
              <h3><span class="result-index">{{ index + 1 }}.</span> {{ displayTitleZh(paper) }}</h3>
              <div class="result-meta">
                <span>{{ displayDate(paper) }}</span>
                <span>{{ paper.source || 'OpenAlex' }}</span>
                <span v-if="paper.match_score !== undefined" class="score-badge">🔥 {{ paper.match_score }}</span>
              </div>
              <p>{{ displayAbstractZh(paper) }}</p>
            </article>
          </div>
          <div v-else-if="!discoverLoading" class="discovery-hint">
            <p v-if="activeTopic">点击「↻ 刷新」从 OpenAlex 获取与研究方向相关的论文推荐。</p>
            <p v-else>请先在今日雷达中配置研究方向关键词，然后点击刷新获取推荐。</p>
          </div>
        </template>
      </section>

      <section v-if="activeTab === 'settings'" class="content-panel form-panel settings-panel">
        <div class="settings-status-grid">
          <span v-for="card in statusCards" :key="card.label" class="status-pill" :class="card.tone">
            {{ card.label }} · {{ card.value }}
          </span>
        </div>
        <label>AI Base URL<input v-model="settings.ai_base_url" placeholder="https://api.deepseek.com" /></label>
        <label>API Key<input v-model="settings.ai_api_key" type="password" :placeholder="settings.has_ai_api_key ? '已保存，留空则不修改' : 'sk-...'" /></label>
        <label>文本模型<input v-model="settings.text_model" placeholder="deepseek-v4-pro" /></label>
        <label>视觉模型<input v-model="settings.vision_model" placeholder="deepseek-v4-pro" /></label>
        <label>Obsidian Vault 路径<input v-model="settings.obsidian_vault_path" placeholder="/path/to/vault" /></label>
        <button class="primary" :disabled="isLoading('settings')" @click="submitSettings">保存设置</button>
      </section>
    </section>
  </main>
</template>

<style scoped>
:global(*) { box-sizing: border-box; }
:global(body) { margin: 0; background: #f6f5fb; }

:global(:root) {
  --ai-purple: #7c3aed;
  --ai-purple-strong: #6d28d9;
  --ai-purple-soft: #f1ebff;
  --ink: #17151f;
  --muted: #6f6b7b;
  --line: #e6e2ef;
  --panel: rgba(255, 255, 255, 0.88);
  --surface: #f6f5fb;
}

.desktop-shell {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  height: 100vh;
  min-height: 0;
  overflow: hidden;
  color: var(--ink);
  background:
    radial-gradient(circle at 22% 0%, rgba(124, 58, 237, 0.09), transparent 30%),
    var(--surface);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  transition: grid-template-columns 0.2s ease;
}
.desktop-shell:has(.sidebar.expanded) {
  grid-template-columns: 232px minmax(0, 1fr);
}

.sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 14px;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.82);
  border-right: 1px solid var(--line);
  height: 100vh;
  overflow: hidden;
  backdrop-filter: blur(20px);
}

.brand-block { display: grid; grid-template-columns: 48px minmax(0, 1fr) 36px; gap: 10px; align-items: center; }
.sidebar:not(.expanded) .brand-block { grid-template-columns: 48px; }
.brand-mark {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 16px;
  color: white;
  background: linear-gradient(135deg, var(--ai-purple), #a855f7);
  box-shadow: 0 12px 28px rgba(124, 58, 237, 0.24);
  font-weight: 800;
}
.brand-copy,
.nav-copy {
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
  transform: translateX(-6px);
  transition: opacity 0.16s ease, transform 0.16s ease;
  white-space: nowrap;
}
.sidebar.expanded .brand-copy,
.sidebar.expanded .nav-copy {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}
.brand-block small, .side-nav small { display: block; margin-top: 4px; color: var(--muted); }
.sidebar-toggle {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  padding: 0;
  color: var(--muted);
  background: #f7f5fb;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.sidebar:not(.expanded) .sidebar-toggle {
  position: absolute;
  top: 66px;
  left: 20px;
  width: 36px;
  height: 28px;
  transform: none;
}
.sidebar:not(.expanded) .side-nav { margin-top: 36px; }
.sidebar-toggle span,
.sidebar-toggle span::before,
.sidebar-toggle span::after {
  display: block;
  width: 14px;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
  content: "";
}
.sidebar-toggle span::before { transform: translateY(-5px); }
.sidebar-toggle span::after { transform: translateY(3px); }
.side-nav { display: grid; gap: 8px; }
.side-nav button {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  width: 100%;
  min-height: 48px;
  padding: 2px;
  text-align: left;
  color: var(--muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 16px;
  overflow: hidden;
}
.sidebar:not(.expanded) .side-nav button {
  grid-template-columns: 42px;
  justify-content: center;
  width: 48px;
  height: 48px;
  min-width: 48px;
  min-height: 48px;
  padding: 2px;
  place-items: center;
}
.side-nav button.active, .side-nav button:hover {
  color: var(--ai-purple-strong);
  background: var(--ai-purple-soft);
  border-color: rgba(124, 58, 237, 0.18);
}
.nav-icon {
  position: relative;
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid var(--line);
}
.sidebar:not(.expanded) .nav-icon {
  width: 42px;
  height: 42px;
  border-radius: 13px;
}
.side-nav button.active .nav-icon {
  color: white;
  background: var(--ai-purple);
  border-color: var(--ai-purple);
}
.nav-icon::before,
.nav-icon::after {
  position: absolute;
  content: "";
  border-color: currentColor;
}
.nav-icon.radar::before {
  width: 18px;
  height: 18px;
  border: 2px solid currentColor;
  border-radius: 999px;
}
.nav-icon.radar::after {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}
.nav-icon.library::before {
  width: 17px;
  height: 21px;
  border: 2px solid currentColor;
  border-radius: 3px;
}
.nav-icon.library::after {
  width: 10px;
  height: 2px;
  background: currentColor;
  box-shadow: 0 5px 0 currentColor;
}
.nav-icon.search::before {
  width: 15px;
  height: 15px;
  border: 2px solid currentColor;
  border-radius: 999px;
  transform: translate(-2px, -2px);
}
.nav-icon.search::after {
  width: 9px;
  height: 2px;
  background: currentColor;
  transform: translate(7px, 8px) rotate(45deg);
}
.nav-icon.settings::before {
  width: 18px;
  height: 18px;
  border: 2px solid currentColor;
  border-radius: 7px;
}
.nav-icon.settings::after {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.workspace {
  min-width: 0;
  height: 100vh;
  min-height: 0;
  padding: 0 24px 24px 24px;
  overflow-y: auto;
}
.topbar {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
  padding-top: 24px;
}
.topbar-title {
  display: flex;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1;
}
.topbar-heading { min-width: 0; }
.topbar-badge {
  padding: 7px 14px;
  border-radius: 999px;
  color: var(--ai-purple-strong);
  background: var(--ai-purple-soft);
  border: 1px solid rgba(124, 58, 237, 0.18);
  font-weight: 800;
  font-size: 13px;
  white-space: nowrap;
  flex-shrink: 0;
}
.topbar-radar-controls {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.topbar-action {
  display: flex;
  justify-content: flex-end;
  min-width: 96px;
}
.detail-topbar {
  position: sticky;
  top: 0;
  z-index: 12;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(96px, 1fr);
  align-items: center;
  width: calc(100% + 48px);
  margin-left: -24px;
  padding: 10px 24px;
  background: var(--surface);
  border-bottom: 1px solid rgba(137, 153, 179, 0.18);
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--ai-purple);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 0; font-size: 26px; line-height: 1.2; }
.muted, .empty-state { color: var(--muted); line-height: 1.7; }

.status-cluster, .button-row, .search-bar, .settings-status-grid, .radar-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.status-pill {
  padding: 8px 12px;
  border-radius: 999px;
  color: var(--muted);
  background: white;
  border: 1px solid var(--line);
  font-size: 13px;
}
.status-pill.success { color: #11633b; background: #e9f8ef; border-color: #bde8cc; }
.status-pill.warning { color: #8a4b0f; background: #fff6df; border-color: #f4d58d; }
.status-pill.error { color: #a2251d; background: #fff0ed; border-color: #ffc9c2; }
.status-pill.info { color: var(--ai-purple-strong); background: var(--ai-purple-soft); border-color: rgba(124, 58, 237, 0.18); }

.toast {
  position: fixed;
  top: 22px;
  right: 24px;
  z-index: 20;
  max-width: 420px;
  padding: 12px 16px;
  border: 1px solid rgba(137, 153, 179, 0.22);
  border-radius: 16px;
  background: white;
  box-shadow: 0 18px 42px rgba(16, 24, 39, 0.18);
}
.toast.success { color: #11633b; }
.toast.warning { color: #8a4b0f; }
.toast.error { color: #a2251d; }
.toast.info { color: var(--ai-purple-strong); }

.page-grid, .library-workbench { display: grid; gap: 18px; }
.page-grid { grid-template-columns: minmax(0, 1fr) 340px; }
.library-workbench { grid-template-columns: minmax(0, 1fr); min-height: calc(100vh - 132px); }
.radar-page { align-items: start; }
.content-panel {
  padding: 22px;
  border: 1px solid rgba(137, 153, 179, 0.22);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 42px rgba(16, 24, 39, 0.08);
}
.settings-panel {
  width: min(100%, 680px);
  max-height: calc(100vh - 132px);
  overflow: auto;
}
.settings-status-grid {
  margin-bottom: 4px;
}
.settings-panel button.primary {
  justify-self: start;
  width: auto;
  padding: 9px 18px;
}
.wide-panel, .reader-pane { min-width: 0; }
.panel-heading, .reader-title {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}
.controls-only {
  justify-content: flex-end;
}
.controls-only:empty {
  display: none;
}
.compact-heading { align-items: center; }

button {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 12px;
  padding: 10px 14px;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}
button:disabled { cursor: not-allowed; opacity: 0.65; }
button.primary { color: white; background: var(--ai-purple); }
button.secondary { color: var(--ai-purple-strong); background: var(--ai-purple-soft); }
button.ghost { color: var(--ai-purple); background: transparent; border: 1px solid rgba(124, 58, 237, 0.22); }
button.danger { color: #a2251d; background: #fff0ed; border: 1px solid #ffc9c2; }
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.7s linear infinite;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

.recommendation-list, .paper-list, .form-panel, .insight-panel, .paper-preview {
  display: grid;
  gap: 12px;
}
.recommendation-card, .search-result-card, .paper-card, .paper-preview, .insight-panel, .edit-strip {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: #ffffff;
}
.recommendation-card { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 16px; }
.recommendation-card > div:first-child {
  display: grid;
  justify-items: center;
  gap: 6px;
}
.recommendation-card > div:first-child small {
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recommendation-title-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
}
.recommendation-title-row h3 { margin-bottom: 8px; }
.recommendation-summary {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
  margin-top: 14px;
  color: var(--muted);
  line-height: 1.65;
}
.score {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  border-radius: 16px;
  color: var(--ai-purple-strong);
  background: var(--ai-purple-soft);
  font-size: 22px;
  font-weight: 800;
}
.idea { color: #11633b; }
.paper-card.selected { border-color: var(--ai-purple); background: var(--ai-purple-soft); }
.paper-card small, .search-result-card small, .reader-title small {
  display: block;
  color: var(--muted);
  line-height: 1.5;
}
.paper-card { cursor: pointer; }
.paper-card-top { display: flex; gap: 12px; justify-content: space-between; align-items: flex-start; }
.paper-title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-height: 1.35;
}
.card-actions { margin-top: 12px; }
.paper-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 9px;
  border-radius: 999px;
  color: var(--ai-purple-strong);
  background: var(--ai-purple-soft);
  border: 1px solid rgba(124, 58, 237, 0.22);
  font-size: 12px;
  font-weight: 700;
}
.score-tag { color: #11633b; background: #e9f8ef; border-color: #bde8cc; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

.paper-detail { display: grid; gap: 18px; align-content: start; }
.library-list-page, .search-panel {
  min-height: calc(100vh - 132px);
  overflow: visible;
}
.search-panel { background: #ffffff; }
.library-card-grid {
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  justify-content: start;
}
.library-paper-card {
  width: 100%;
  cursor: pointer;
}
.library-breadcrumb {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--muted);
  font-weight: 800;
  min-width: 0;
}
.library-breadcrumb strong {
  min-width: 0;
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-breadcrumb {
  justify-self: start;
  width: 100%;
}
.detail-breadcrumb button {
  flex: 0 0 auto;
}
.edit-strip { display: grid; gap: 12px; margin-bottom: 0; }
.reader-tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--line); padding-bottom: 10px; }
.detail-tabs {
  justify-self: center;
  margin: 0;
  padding: 0;
  border-bottom: 0;
}
.reader-tabs button { color: var(--muted); background: transparent; }
.reader-tabs button.active { color: var(--ink); background: white; border-bottom: 3px solid var(--ink); border-radius: 0; }
.single-reader { min-height: calc(100vh - 240px); }
.summary-hero {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 28px;
  align-items: center;
}
.paper-cover {
  display: grid;
  align-content: center;
  justify-items: center;
  min-height: 260px;
  border: 1px solid var(--line);
  border-radius: 14px;
  color: var(--muted);
  background: linear-gradient(180deg, #ffffff 0%, #f5f7fb 100%);
  box-shadow: inset 0 0 0 10px #f9fbff;
  text-align: center;
}
.paper-cover strong { max-width: 150px; overflow-wrap: anywhere; color: var(--ink); }
.paper-meta { display: grid; gap: 14px; }
.paper-meta h2 { margin-bottom: 0; font-size: 28px; line-height: 1.25; }
.paper-meta h3 { margin-bottom: 4px; color: var(--muted); font-size: 20px; line-height: 1.35; }
.author-row, .link-row, .meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.author-row span {
  padding: 7px 12px;
  border-radius: 12px;
  color: #344054;
  background: #e8edf5;
  font-weight: 700;
}
.link-row a {
  color: var(--ai-purple-strong);
  font-weight: 700;
  text-decoration: none;
}
.link-row a + a::before {
  content: "|";
  margin-right: 10px;
  color: #c4ccda;
}
.meta-row span {
  color: var(--muted);
  font-weight: 700;
}
.meta-row span + span::before {
  content: "|";
  margin-right: 10px;
  color: #c4ccda;
}
.abstract-card { display: grid; gap: 18px; font-size: 18px; line-height: 1.8; }
.abstract-card h2 { margin: 0; text-align: center; color: #344054; }
.abstract-card p { margin: 0; }
.note-section {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid #e4ebf7;
  border-radius: 16px;
  background: white;
}
.note-label {
  color: var(--ai-purple-strong);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.note-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 20px;
}
.note-list li { line-height: 1.65; }
.pdf-render-panel {
  min-height: 300px;
  overflow: visible;
  padding: 0;
}
.pdf-embed-frame {
  display: block;
  width: 100%;
  height: calc(100vh - 120px);
  border: 0;
  border-radius: 14px;
}
.abstract-details { margin-top: 12px; color: #344054; }
.abstract-details summary { cursor: pointer; font-weight: 800; }
dl { display: grid; gap: 10px; }
dt { color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.insight-panel pre {
  max-height: none;
  overflow: visible;
  white-space: pre-wrap;
  padding: 16px;
  border-radius: 16px;
  background: #101827;
  color: #eef4ff;
}
.note-rendered {
  display: grid;
  gap: 14px;
  max-height: none;
  overflow: visible;
  padding: 20px;
  border: 1px solid #e6e2ef;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fbf9ff 100%);
  color: #252033;
  line-height: 1.75;
}
.note-rendered p {
  margin: 0;
  color: #3b3548;
}
.note-heading {
  margin: 8px 0 0;
  color: var(--ink);
  line-height: 1.35;
}
.note-heading.level-1 { font-size: 24px; }
.note-heading.level-2 { font-size: 20px; }
.note-heading.level-3,
.note-heading.level-4 { font-size: 17px; color: var(--ai-purple-strong); }
.note-render-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.note-render-list li {
  position: relative;
  padding: 12px 14px 12px 34px;
  border: 1px solid rgba(124, 58, 237, 0.14);
  border-radius: 14px;
  background: rgba(241, 235, 255, 0.42);
}
.note-render-list li::before {
  position: absolute;
  left: 14px;
  top: 20px;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--ai-purple);
  content: "";
}
.markdown-target {
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--ai-purple-strong);
  background: var(--ai-purple-soft);
  overflow-wrap: anywhere;
  font-weight: 700;
}
.search-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}
.search-bar input { max-width: 420px; flex: 1; }
.search-bar button { flex-shrink: 0; }
.search-result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
  align-items: start;
  justify-content: stretch;
}
.search-result-card {
  position: relative;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 16px;
  width: 100%;
  height: 200px;
  overflow: hidden;
  padding: 20px 52px 18px 20px;
  margin-top: 0;
  box-shadow: 0 10px 24px rgba(16, 24, 39, 0.12);
}
.search-result-card h3 {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  margin: 0;
  font-size: 17px;
  line-height: 1.4;
}
.search-result-card p {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  margin: 0;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.55;
}
.result-index { color: #9aa8bd; }
.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--muted);
  font-weight: 700;
}
.result-meta span + span::before {
  content: "-";
  margin-right: 8px;
  color: #9aa8bd;
}
.score-badge {
  padding: 5px 10px;
  border-radius: 999px;
  color: #ff6900;
  background: #fff4e8;
}
.discovery-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.discovery-title {
  font-weight: 800;
  color: var(--ai-purple-strong);
}
.discovery-hint {
  padding: 40px 0;
  text-align: center;
  color: var(--muted);
  line-height: 1.7;
}
.result-card-actions {
  position: absolute;
  top: 20px;
  right: 18px;
  display: grid;
  gap: 12px;
}
.icon-button {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  padding: 0;
  color: var(--muted);
  background: transparent;
  border: 0;
  text-decoration: none;
  font-size: 22px;
}
.icon-button.saved {
  color: #ff6900;
}
label { display: grid; gap: 6px; color: #344054; font-weight: 700; }
input, textarea, select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 11px 12px;
  color: var(--ink);
  background: white;
  font: inherit;
}
textarea { min-height: 96px; }

.radar-controls {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.topic-side-panel {
  align-self: start;
  height: 420px;
  overflow: auto;
}
.radar-limit-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  align-items: center;
  min-width: 260px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #ffffff;
}
.radar-limit-row input { width: 76px; }
.result-count {
  margin-bottom: 10px;
  color: var(--ai-purple-strong);
  font-weight: 800;
}
.highlight {
  padding: 0 2px;
  border-radius: 4px;
  background: #fff1a8;
}
@media (max-width: 1080px) {
  .page-grid, .library-workbench { grid-template-columns: 1fr; }
  .summary-hero { grid-template-columns: 1fr; }
  .search-bar { flex-wrap: wrap; }
}
</style>
