<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchHealth, type HealthPayload } from './api/health';
import {
  analyzePaperStructure,
  createPaper,
  createTopic,
  deletePaper,
  deleteTopic,
  fetchLocalSettings,
  fetchPaperMarkdown,
  fetchPapers,
  fetchTodayRadar,
  fetchTopics,
  runRadar,
  saveLocalSettings,
  searchPapers,
  updatePaper,
  updateTopic,
  type LocalSettingsPayload,
  type MarkdownPreview,
  type Paper,
  type Recommendation,
  type ResearchTopic,
} from './api/litradar';

type Workspace = 'radar' | 'library' | 'search' | 'topics' | 'settings';
type NotificationTone = 'info' | 'success' | 'warning' | 'error';
type ReaderMode = 'original' | 'note' | 'markdown';

interface NotificationItem {
  id: number;
  tone: NotificationTone;
  message: string;
}

interface NavItem {
  id: Workspace;
  label: string;
  description: string;
}

const navItems: NavItem[] = [
  { id: 'radar', label: '今日雷达', description: '每日推荐' },
  { id: 'library', label: '论文库', description: '知识库工作台' },
  { id: 'search', label: '论文搜索', description: 'arXiv 检索' },
  { id: 'topics', label: '研究方向', description: '关键词配置' },
  { id: 'settings', label: '设置', description: '本地服务' },
];

const health = ref<HealthPayload | null>(null);
const activeTab = ref<Workspace>('library');
const loadingAction = ref<string | null>(null);
const notification = ref<NotificationItem | null>(null);
const notificationTimer = ref<ReturnType<typeof setTimeout> | null>(null);
const topics = ref<ResearchTopic[]>([]);
const papers = ref<Paper[]>([]);
const recommendations = ref<Recommendation[]>([]);
const searchResults = ref<Paper[]>([]);
const selectedTopicId = ref<number | null>(null);
const selectedPaperId = ref<number | null>(null);
const editingTopicId = ref<number | null>(null);
const editingPaperId = ref<number | null>(null);
const readerMode = ref<ReaderMode>('original');
const radarLimit = ref(3);
const topicModalOpen = ref(false);
const radarLimitEditing = ref(false);
const radarLimitDraft = ref(3);
const venueOptions = [
  { group: 'CCF-A', name: 'CVPR' },
  { group: 'CCF-A', name: 'ICCV' },
  { group: 'CCF-A', name: 'NeurIPS' },
  { group: 'CCF-A', name: 'ICML' },
  { group: 'CCF-A', name: 'AAAI' },
  { group: 'CCF-A', name: 'IJCAI' },
  { group: 'CCF-A', name: 'TPAMI' },
  { group: 'CCF-B', name: 'ECCV' },
  { group: 'CCF-B', name: 'ICLR' },
  { group: 'CCF-B', name: 'ACM MM' },
  { group: 'CCF-B', name: 'TNNLS' },
  { group: 'CCF-B', name: 'Pattern Recognition' },
];
const markdownPreview = ref<MarkdownPreview | null>(null);
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
  venues: [] as string[],
});

const paperForm = ref({
  title: '',
  status: 'saved',
  topic: null as number | null,
  local_pdf_path: '',
});

const searchForm = ref({
  query: 'remote sensing change detection',
  topicId: null as number | null,
});

const selectedPaper = computed(() => papers.value.find((paper) => paper.id === selectedPaperId.value) ?? null);
const activeTopic = computed(() => topics.value.find((topic) => topic.id === selectedTopicId.value) ?? null);
const hasApiKey = computed(() => Boolean(settings.value.has_ai_api_key || settings.value.ai_api_key));
const hasObsidian = computed(() => Boolean(settings.value.obsidian_vault_path));
const statusCards = computed(() => [
  { label: '本地后端', value: health.value ? '已连接' : '未连接', tone: health.value ? 'success' : 'error' },
  { label: '当前方向', value: activeTopic.value?.name ?? '未选择', tone: activeTopic.value ? 'success' : 'warning' },
  { label: 'AI 中转站', value: hasApiKey.value ? 'Key 已配置' : '未配置', tone: hasApiKey.value ? 'success' : 'warning' },
  { label: 'Obsidian', value: hasObsidian.value ? '已配置' : '仅预览', tone: hasObsidian.value ? 'success' : 'warning' },
]);
const workspaceTitle = computed(() => navItems.find((item) => item.id === activeTab.value)?.label ?? '工作台');
const workspaceSubtitle = computed(() => navItems.find((item) => item.id === activeTab.value)?.description ?? 'LitRadar');

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

function resetTopicForm() {
  editingTopicId.value = null;
  topicForm.value = {
    name: '',
    keywordsText: '',
    venues: [],
  };
}

function openNewTopicModal() {
  resetTopicForm();
  topicModalOpen.value = true;
}

function editTopic(topic: ResearchTopic) {
  editingTopicId.value = topic.id;
  topicForm.value = {
    name: topic.name,
    keywordsText: topic.keywords.join('\n'),
    venues: topic.arxiv_categories,
  };
  topicModalOpen.value = true;
}

function selectCurrentTopic(topicId: number) {
  selectedTopicId.value = topicId;
  searchForm.value.topicId = topicId;
  pushNotification('当前研究方向已切换。', 'info');
}

function selectPaper(paperId?: number | null) {
  selectedPaperId.value = paperId ?? null;
  markdownPreview.value = null;
  readerMode.value = 'original';
  editingPaperId.value = null;
  activeTab.value = 'library';
}

function editPaper(paper: Paper) {
  editingPaperId.value = paper.id ?? null;
  paperForm.value = {
    title: paper.title,
    status: paper.status || 'saved',
    topic: paper.topic,
    local_pdf_path: paper.local_pdf_path || '',
  };
  selectPaper(paper.id);
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
  return value.split('\n').map((item) => item.replace(/^-\s*/, '').trim()).filter(Boolean);
}

function noteText(value?: string | string[]): string {
  if (Array.isArray(value)) return value.join('；');
  return value || '待分析。';
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
  recommendations.value = radarPayload;
  if (!selectedTopicId.value || !topicsPayload.some((topic) => topic.id === selectedTopicId.value)) {
    selectedTopicId.value = topicsPayload[0]?.id ?? null;
  }
  if (!searchForm.value.topicId || !topicsPayload.some((topic) => topic.id === searchForm.value.topicId)) {
    searchForm.value.topicId = selectedTopicId.value;
  }
  if (!selectedPaperId.value || !papersPayload.some((paper) => paper.id === selectedPaperId.value)) {
    selectedPaperId.value = papersPayload[0]?.id ?? null;
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

async function submitTopic() {
  await withLoading('topic-save', async () => {
    const payload = {
      name: topicForm.value.name,
      description: '',
      keywords: lines(topicForm.value.keywordsText),
      arxiv_categories: topicForm.value.venues,
      obsidian_folder: '',
      enabled: true,
    };
    const topic = editingTopicId.value
      ? await updateTopic(editingTopicId.value, payload)
      : await createTopic({ ...payload, daily_limit: 3 });
    await refreshCollections();
    selectedTopicId.value = topic.id;
    searchForm.value.topicId = topic.id;
    resetTopicForm();
    topicModalOpen.value = false;
    pushNotification(`研究方向「${topic.name}」已保存。`, 'success');
  });
}

async function removeTopic(topic: ResearchTopic) {
  if (!window.confirm(`确认删除研究方向「${topic.name}」？相关论文会保留但取消方向关联。`)) return;
  await withLoading(`topic-delete-${topic.id}`, async () => {
    await deleteTopic(topic.id);
    await refreshCollections();
    pushNotification('研究方向已删除。', 'success');
  });
}

async function submitSearch() {
  await withLoading('search', async () => {
    searchResults.value = await searchPapers(searchForm.value.query, searchForm.value.topicId);
    pushNotification(`找到 ${searchResults.value.length} 篇候选论文。`, 'success');
  });
}

async function savePaper(paper: Paper) {
  await withLoading(`save-paper-${paper.arxiv_id || paper.title}`, async () => {
    const saved = await createPaper({ ...paper, topic: searchForm.value.topicId });
    await refreshCollections();
    selectPaper(saved.id);
    pushNotification('论文已保存到论文库。', 'success');
  });
}

async function submitPaperEdit() {
  if (!editingPaperId.value) return;
  await withLoading('paper-save', async () => {
    await updatePaper(editingPaperId.value as number, {
      title: paperForm.value.title,
      status: paperForm.value.status,
      topic: paperForm.value.topic,
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
    markdownPreview.value = null;
    pushNotification('论文已删除。', 'success');
  });
}

async function submitRadar() {
  if (!activeTopic.value) {
    pushNotification('请先选择一个当前研究方向。', 'warning');
    return;
  }
  await withLoading('radar', async () => {
    const payload = await runRadar(activeTopic.value!.id, radarLimit.value);
    await refreshCollections();
    pushNotification(`${payload.topic.name} 今日雷达生成 ${payload.recommendations.length} 篇推荐。`, 'success');
  });
}

async function analyzeSelectedPaper() {
  if (!selectedPaperId.value) return;
  await withLoading('analyze', async () => {
    await analyzePaperStructure(selectedPaperId.value as number);
    await refreshCollections();
    readerMode.value = 'note';
    pushNotification('结构化阅读笔记已生成。', 'success');
  });
}

async function previewSelectedPaperMarkdown() {
  if (!selectedPaperId.value) return;
  await withLoading('markdown', async () => {
    markdownPreview.value = await fetchPaperMarkdown(selectedPaperId.value as number);
    readerMode.value = 'markdown';
    pushNotification('Markdown 预览已更新。', 'info');
  });
}

onMounted(loadAll);
</script>

<template>
  <main class="desktop-shell">
    <aside class="sidebar">
      <div class="brand-block">
        <span class="brand-mark">LR</span>
        <div>
          <strong>LitRadar</strong>
          <small>个人文献雷达</small>
        </div>
      </div>

      <nav class="side-nav">
        <button v-for="item in navItems" :key="item.id" :class="{ active: activeTab === item.id }" @click="activeTab = item.id">
          <span>{{ item.label }}</span>
          <small>{{ item.description }}</small>
        </button>
      </nav>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ workspaceSubtitle }}</p>
          <h1>{{ workspaceTitle }}</h1>
        </div>
        <div class="status-cluster">
          <span v-for="card in statusCards" :key="card.label" class="status-pill" :class="card.tone">
            {{ card.label }} · {{ card.value }}
          </span>
          <span v-if="loadingAction" class="status-pill info"><span class="spinner" />处理中</span>
        </div>
      </header>

      <article v-if="notification" class="toast" :class="notification.tone">
        {{ notification.message }}
      </article>

      <section v-if="activeTab === 'radar'" class="page-grid radar-page">
        <div class="content-panel wide-panel">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">Daily Radar</p>
              <h2>{{ activeTopic ? activeTopic.name : '选择一个当前方向' }}</h2>
              <p class="muted">今日雷达只更新当前选定方向，不再遍历所有方向。</p>
            </div>
            <div class="radar-controls">
              <div class="radar-limit-row">
                <span>每日推荐数量</span>
                <strong v-if="!radarLimitEditing">{{ radarLimit }}</strong>
                <input v-else v-model.number="radarLimitDraft" type="number" min="1" max="10" />
                <button v-if="!radarLimitEditing" class="ghost" @click="startRadarLimitEdit">编辑</button>
                <button v-else class="primary" @click="saveRadarLimit">保存</button>
              </div>
              <button class="primary" :disabled="!activeTopic || isLoading('radar')" @click="submitRadar">
                <span v-if="isLoading('radar')" class="spinner" />{{ isLoading('radar') ? '更新中' : '更新今日推荐' }}
              </button>
            </div>
          </div>
          <div v-if="recommendations.length" class="recommendation-list">
            <article v-for="item in recommendations" :key="item.id" class="recommendation-card">
              <div>
                <span class="score">{{ item.score }}</span>
                <small>{{ item.topic.name }}</small>
              </div>
              <section>
                <h3>{{ item.paper.title }}</h3>
                <p>{{ item.reason }}</p>
                <p class="idea">{{ item.idea_hint }}</p>
                <button class="ghost" @click="selectPaper(item.paper.id)">打开论文工作区</button>
              </section>
            </article>
          </div>
          <div v-else class="empty-state">还没有今日推荐。选择当前方向并设置数量后，点击更新今日推荐。</div>
        </div>

        <aside class="content-panel topic-side-panel">
          <p class="eyebrow">当前方向</p>
          <article v-if="activeTopic" class="topic-mini-card selected">
            <strong>{{ activeTopic.name }}</strong>
            <small>{{ activeTopic.keywords.join(' / ') || '无关键词' }}</small>
            <button class="ghost" @click="activeTab = 'topics'">管理方向</button>
          </article>
          <button v-else class="add-card small-add" @click="activeTab = 'topics'">
            <span>+</span>
            新增研究方向
          </button>
        </aside>
      </section>

      <section v-if="activeTab === 'library'" class="library-workbench">
        <aside class="paper-list content-panel">
          <div class="panel-heading compact-heading">
            <div>
              <p class="eyebrow">Library</p>
              <h2>论文知识库</h2>
            </div>
            <span>{{ papers.length }} 篇</span>
          </div>
          <article v-for="paper in papers" :key="paper.id" class="paper-card" :class="{ selected: selectedPaperId === paper.id }" @click="selectPaper(paper.id)">
            <div class="paper-card-top">
              <strong class="paper-title">{{ paper.title }}</strong>
              <span>{{ paper.year || '未知年份' }}</span>
            </div>
            <small>{{ paper.status || 'saved' }} · {{ formatAuthors(paper.authors) }}</small>
            <div v-if="paper.tags?.length" class="tag-row">
              <span v-for="tag in paper.tags" :key="tag" class="paper-tag">{{ tag }}</span>
            </div>
            <div class="button-row card-actions">
              <button class="ghost" @click.stop="editPaper(paper)">编辑</button>
              <button class="danger" :disabled="isLoading(`paper-delete-${paper.id}`)" @click.stop="removePaper(paper)">删除</button>
            </div>
          </article>
          <div v-if="!papers.length" class="empty-state">还没有保存论文。先从论文搜索或今日雷达保存候选论文。</div>
        </aside>

        <section class="reader-pane content-panel" v-if="selectedPaper">
          <div class="reader-title">
            <div>
              <p class="eyebrow">Paper Workspace</p>
              <h2>{{ selectedPaper.title }}</h2>
              <small>{{ formatAuthors(selectedPaper.authors) }} · {{ selectedPaper.year || '未知年份' }}</small>
            </div>
            <div class="button-row">
              <button class="secondary" :disabled="isLoading('analyze')" @click="analyzeSelectedPaper">
                <span v-if="isLoading('analyze')" class="spinner" />结构化阅读
              </button>
              <button class="secondary" :disabled="isLoading('markdown')" @click="previewSelectedPaperMarkdown">
                <span v-if="isLoading('markdown')" class="spinner" />Markdown 预览
              </button>
            </div>
          </div>

          <form v-if="editingPaperId" class="edit-strip" @submit.prevent="submitPaperEdit">
            <label>标题<input v-model="paperForm.title" /></label>
            <label>状态<input v-model="paperForm.status" /></label>
            <label>研究方向
              <select v-model="paperForm.topic">
                <option :value="null">未分类</option>
                <option v-for="topic in topics" :key="topic.id" :value="topic.id">{{ topic.name }}</option>
              </select>
            </label>
            <label>本地 PDF<input v-model="paperForm.local_pdf_path" /></label>
            <div class="button-row">
              <button class="primary" type="submit" :disabled="isLoading('paper-save')">保存论文</button>
              <button class="ghost" type="button" @click="editingPaperId = null">取消</button>
            </div>
          </form>

          <div class="reader-tabs">
            <button :class="{ active: readerMode === 'original' }" @click="readerMode = 'original'">原文预览</button>
            <button :class="{ active: readerMode === 'note' }" @click="readerMode = 'note'">结构化笔记</button>
            <button :class="{ active: readerMode === 'markdown' }" @click="readerMode = 'markdown'">Markdown</button>
          </div>

          <article v-if="readerMode === 'original'" class="paper-preview single-reader">
            <div class="pdf-reader-frame" v-if="selectedPaper.pdf_url">
              <iframe :src="selectedPaper.pdf_url" title="PDF reader"></iframe>
            </div>
            <p v-else>{{ selectedPaper.abstract || '暂无摘要。后续这里可接入 PDF 原文预览与关键图浏览。' }}</p>
            <details v-if="selectedPaper.abstract" class="abstract-details">
              <summary>摘要</summary>
              <p>{{ selectedPaper.abstract }}</p>
            </details>
            <dl>
              <div><dt>arXiv</dt><dd>{{ selectedPaper.arxiv_id || '无' }}</dd></div>
              <div><dt>PDF</dt><dd>{{ selectedPaper.pdf_url || '未关联' }}</dd></div>
              <div><dt>本地 PDF</dt><dd>{{ selectedPaper.local_pdf_path || '未关联' }}</dd></div>
            </dl>
          </article>

          <article v-if="readerMode === 'note'" class="insight-panel single-reader">
            <template v-if="selectedPaper.insight">
              <section class="note-section">
                <span class="note-label">研究方向</span>
                <p>{{ selectedPaper.insight.research_direction || '未分类方向' }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">任务定义</span>
                <p>{{ selectedPaper.insight.task_definition || '待分析。' }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">创新点</span>
                <ul v-if="noteList(selectedPaper.insight.innovation_points).length" class="note-list">
                  <li v-for="item in noteList(selectedPaper.insight.innovation_points)" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ noteText(selectedPaper.insight.innovation_points) }}</p>
              </section>
              <section class="note-section">
                <span class="note-label">贴近当前方向的 idea</span>
                <ul v-if="noteList(selectedPaper.insight.idea_hints).length" class="note-list">
                  <li v-for="item in noteList(selectedPaper.insight.idea_hints)" :key="item">{{ item }}</li>
                </ul>
                <p v-else>{{ noteText(selectedPaper.insight.idea_hints) }}</p>
              </section>
            </template>
            <p v-else class="empty-state">还没有结构化阅读结果。点击“结构化阅读”生成第一版笔记。</p>
          </article>

          <section v-if="readerMode === 'markdown'" class="markdown-preview single-reader">
            <div v-if="markdownPreview" class="panel-heading compact-heading">
              <h3>Obsidian Markdown</h3>
              <span>{{ markdownPreview.target_relative_path }}</span>
            </div>
            <pre v-if="markdownPreview">{{ markdownPreview.markdown }}</pre>
            <p v-else class="empty-state">点击“Markdown 预览”生成内容。</p>
          </section>
        </section>

        <section v-else class="reader-pane content-panel empty-reader">
          <h2>选择一篇论文开始阅读</h2>
          <p>中间工作区会用于论文原文预览、结构化笔记和 Markdown 输出。</p>
        </section>
      </section>

      <section v-if="activeTab === 'search'" class="content-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">arXiv Search</p>
            <h2>论文搜索</h2>
          </div>
          <button class="primary" :disabled="isLoading('search')" @click="submitSearch">
            <span v-if="isLoading('search')" class="spinner" />{{ isLoading('search') ? '搜索中' : '搜索' }}
          </button>
        </div>
        <div v-if="searchResults.length" class="result-count">共找到 {{ searchResults.length }} 篇候选论文</div>
        <div class="search-bar">
          <input v-model="searchForm.query" placeholder="输入关键词，例如 remote sensing classify" />
          <select v-model="searchForm.topicId">
            <option :value="null">不绑定方向</option>
            <option v-for="topic in topics" :key="topic.id" :value="topic.id">{{ topic.name }}</option>
          </select>
        </div>
        <article v-for="paper in searchResults" :key="paper.arxiv_id || paper.title" class="search-result-card">
          <div>
            <h3><span v-for="part in highlightedParts(paper.title, paper.matched_terms)" :key="`${paper.arxiv_id}-title-${part.text}`" :class="{ highlight: part.match }">{{ part.text }}</span></h3>
            <div class="tag-row" v-if="paper.tags?.length">
              <span v-for="tag in paper.tags" :key="tag" class="paper-tag">{{ tag }}</span>
              <span v-if="paper.match_score !== undefined" class="paper-tag score-tag">匹配 {{ paper.match_score }}</span>
            </div>
            <p><span v-for="part in highlightedParts(paper.abstract, paper.matched_terms)" :key="`${paper.arxiv_id}-abstract-${part.text}`" :class="{ highlight: part.match }">{{ part.text }}</span></p>
            <small>{{ formatAuthors(paper.authors) }} · {{ paper.year || '未知年份' }}</small>
          </div>
          <button class="secondary" :disabled="isLoading(`save-paper-${paper.arxiv_id || paper.title}`)" @click="savePaper(paper)">保存</button>
        </article>
      </section>

      <section v-if="activeTab === 'topics'" class="topics-layout">
        <section class="topic-card-grid">
          <article v-if="activeTopic" class="topic-card selected current-topic-card">
            <div>
              <p class="eyebrow">当前方向</p>
              <h3>{{ activeTopic.name }}</h3>
              <small>{{ activeTopic.keywords.join(' / ') || '无关键词' }}</small>
              <small>{{ activeTopic.arxiv_categories.join(' / ') || '未选择会议或期刊' }}</small>
            </div>
            <div class="button-row card-actions">
              <button class="ghost" @click="editTopic(activeTopic)">编辑</button>
              <button class="danger" :disabled="isLoading(`topic-delete-${activeTopic.id}`)" @click="removeTopic(activeTopic)">删除</button>
            </div>
          </article>

          <article v-for="topic in topics.filter((item) => item.id !== selectedTopicId)" :key="topic.id" class="topic-card">
            <div>
              <p class="eyebrow">Research Topic</p>
              <h3>{{ topic.name }}</h3>
              <small>{{ topic.keywords.join(' / ') || '无关键词' }}</small>
              <small>{{ topic.arxiv_categories.join(' / ') || '未选择会议或期刊' }}</small>
            </div>
            <div class="button-row card-actions">
              <button class="primary" @click="selectCurrentTopic(topic.id)">设为当前</button>
              <button class="ghost" @click="editTopic(topic)">编辑</button>
              <button class="danger" :disabled="isLoading(`topic-delete-${topic.id}`)" @click="removeTopic(topic)">删除</button>
            </div>
          </article>

          <button class="add-card" @click="openNewTopicModal">
            <span>+</span>
            新增方向
          </button>
        </section>
      </section>

      <div v-if="topicModalOpen" class="modal-backdrop">
        <form class="modal-card" @submit.prevent="submitTopic">
          <div class="panel-heading compact-heading">
            <h2>{{ editingTopicId ? '编辑研究方向' : '新增研究方向' }}</h2>
            <button class="ghost" type="button" @click="topicModalOpen = false">关闭</button>
          </div>
          <label>名称<input v-model="topicForm.name" /></label>
          <label>关键词（每行一个）<textarea v-model="topicForm.keywordsText" /></label>
          <p class="eyebrow">会议 / 期刊偏好</p>
          <div class="venue-grid">
            <label v-for="venue in venueOptions" :key="venue.name" class="check-card">
              <input v-model="topicForm.venues" type="checkbox" :value="venue.name" />
              <span>{{ venue.group }} · {{ venue.name }}</span>
            </label>
          </div>
          <div class="button-row">
            <button class="primary" type="submit" :disabled="isLoading('topic-save')">
              <span v-if="isLoading('topic-save')" class="spinner" />保存
            </button>
            <button class="ghost" type="button" @click="topicModalOpen = false">取消</button>
          </div>
        </form>
      </div>

      <section v-if="activeTab === 'settings'" class="content-panel form-panel settings-panel">
        <p class="eyebrow">Local Settings</p>
        <h2>本地配置</h2>
        <div class="settings-summary">
          <span :class="{ ready: hasApiKey }">AI Key：{{ hasApiKey ? '已绑定' : '未配置' }}</span>
          <span :class="{ ready: hasObsidian }">Obsidian：{{ hasObsidian ? '已配置' : '未配置，仅预览' }}</span>
        </div>
        <label>AI 中转站 Base URL<input v-model="settings.ai_base_url" placeholder="https://.../v1" /></label>
        <label>API Key<input v-model="settings.ai_api_key" type="password" :placeholder="settings.has_ai_api_key ? '已保存，留空则不修改' : 'sk-...'" /></label>
        <label>文本模型<input v-model="settings.text_model" placeholder="claude-sonnet-4-6" /></label>
        <label>视觉模型<input v-model="settings.vision_model" placeholder="claude-opus-4-7" /></label>
        <label>Obsidian Vault 路径<input v-model="settings.obsidian_vault_path" placeholder="/path/to/vault" /></label>
        <button class="primary" :disabled="isLoading('settings')" @click="submitSettings">保存设置</button>
      </section>
    </section>
  </main>
</template>

<style scoped>
:global(*) { box-sizing: border-box; }
:global(body) { margin: 0; background: #101827; }

.desktop-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  height: 100vh;
  min-height: 0;
  color: #172033;
  background: #e9eef7;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px;
  color: #eef4ff;
  background: linear-gradient(180deg, #111827 0%, #172033 100%);
  height: 100vh;
  overflow: hidden;
}

.brand-block { display: flex; gap: 12px; align-items: center; }
.brand-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 14px;
  color: white;
  background: #3563e9;
  font-weight: 800;
}
.brand-block small, .side-nav small { display: block; margin-top: 4px; color: #9aa8bd; }
.side-nav { display: grid; gap: 8px; }
.side-nav button {
  display: grid;
  gap: 2px;
  width: 100%;
  padding: 14px 16px;
  text-align: left;
  color: #d8e2f3;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 14px;
}
.side-nav button.active, .side-nav button:hover {
  color: white;
  background: rgba(53, 99, 233, 0.22);
  border-color: rgba(111, 143, 255, 0.35);
}

.workspace {
  min-width: 0;
  height: 100vh;
  min-height: 0;
  padding: 24px;
  overflow-y: auto;
}
.topbar {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}
.eyebrow {
  margin: 0 0 6px;
  color: #3563e9;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 0; font-size: 34px; }
.muted, .empty-state { color: #6a7688; line-height: 1.7; }

.status-cluster, .button-row, .search-bar, .settings-summary, .radar-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.status-pill, .settings-summary span {
  padding: 8px 12px;
  border-radius: 999px;
  color: #48566a;
  background: white;
  border: 1px solid #dce4f2;
  font-size: 13px;
}
.status-pill.success, .settings-summary .ready { color: #11633b; background: #e9f8ef; border-color: #bde8cc; }
.status-pill.warning { color: #8a4b0f; background: #fff6df; border-color: #f4d58d; }
.status-pill.error { color: #a2251d; background: #fff0ed; border-color: #ffc9c2; }
.status-pill.info { color: #214fc2; background: #edf3ff; border-color: #cbd9ff; }

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
.toast.info { color: #214fc2; }

.page-grid, .library-workbench, .topics-layout { display: grid; gap: 18px; }
.page-grid { grid-template-columns: minmax(0, 1fr) 340px; }
.library-workbench { grid-template-columns: minmax(320px, 430px) minmax(0, 1fr); min-height: calc(100vh - 132px); }
.topics-layout { align-items: start; }
.content-panel {
  padding: 22px;
  border: 1px solid rgba(137, 153, 179, 0.22);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 42px rgba(16, 24, 39, 0.08);
}
.wide-panel, .reader-pane { min-width: 0; }
.panel-heading, .reader-title {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
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
button.primary { color: white; background: #3563e9; }
button.secondary { color: #214fc2; background: #edf3ff; }
button.ghost { color: #3563e9; background: transparent; border: 1px solid #cbd9ff; }
button.danger { color: #a2251d; background: #fff0ed; border: 1px solid #ffc9c2; }
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.recommendation-list, .paper-list, .form-panel, .insight-panel, .paper-preview, .topic-card-grid {
  display: grid;
  gap: 12px;
}
.recommendation-card, .search-result-card, .topic-mini-card, .paper-card, .paper-preview, .insight-panel, .topic-card, .add-card, .edit-strip {
  padding: 16px;
  border: 1px solid #dce4f2;
  border-radius: 18px;
  background: #fbfdff;
}
.recommendation-card { display: grid; grid-template-columns: 74px minmax(0, 1fr); gap: 16px; }
.score {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  border-radius: 16px;
  color: #214fc2;
  background: #edf3ff;
  font-size: 22px;
  font-weight: 800;
}
.idea { color: #11633b; }
.topic-mini-card.selected, .topic-card.selected, .paper-card.selected { border-color: #3563e9; background: #f2f6ff; }
.topic-card-grid { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.topic-card { min-height: 220px; display: flex; flex-direction: column; justify-content: space-between; }
.topic-card small, .topic-mini-card small, .paper-card small, .search-result-card small, .reader-title small {
  display: block;
  color: #6a7688;
  line-height: 1.5;
}
.add-card {
  min-height: 220px;
  color: #3563e9;
  background: rgba(237, 243, 255, 0.8);
  border: 1px dashed #8ba7ff;
  font-size: 16px;
}
.add-card span { font-size: 32px; line-height: 1; }
.small-add { min-height: 110px; width: 100%; }

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
  color: #214fc2;
  background: #edf3ff;
  border: 1px solid #cbd9ff;
  font-size: 12px;
  font-weight: 700;
}
.score-tag { color: #11633b; background: #e9f8ef; border-color: #bde8cc; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

.edit-strip { display: grid; gap: 12px; margin-bottom: 16px; }
.reader-tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid #dce4f2; padding-bottom: 10px; }
.reader-tabs button { color: #48566a; background: transparent; }
.reader-tabs button.active { color: #214fc2; background: #edf3ff; }
.single-reader { min-height: 540px; }
.note-section {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid #e4ebf7;
  border-radius: 16px;
  background: white;
}
.note-label {
  color: #214fc2;
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
.pdf-reader-frame {
  height: 62vh;
  min-height: 460px;
  overflow: hidden;
  border: 1px solid #dce4f2;
  border-radius: 14px;
  background: #101827;
}
.pdf-reader-frame iframe { width: 100%; height: 100%; border: 0; }
.abstract-details { margin-top: 12px; color: #344054; }
.abstract-details summary { cursor: pointer; font-weight: 800; }
dl { display: grid; gap: 10px; }
dt { color: #6a7688; font-size: 12px; font-weight: 800; text-transform: uppercase; }
dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.markdown-preview pre {
  max-height: 68vh;
  overflow: auto;
  white-space: pre-wrap;
  padding: 16px;
  border-radius: 16px;
  background: #101827;
  color: #eef4ff;
}
.search-bar { display: grid; grid-template-columns: minmax(220px, 1fr) 260px; margin-bottom: 16px; }
.search-result-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 16px; align-items: start; margin-top: 12px; }
label { display: grid; gap: 6px; color: #344054; font-weight: 700; }
input, textarea, select {
  width: 100%;
  border: 1px solid #ccd8f6;
  border-radius: 12px;
  padding: 11px 12px;
  color: #172033;
  background: white;
  font: inherit;
}
textarea { min-height: 96px; }

.radar-controls {
  flex-direction: column;
  align-items: stretch;
}
.radar-limit-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  align-items: center;
  min-width: 260px;
  padding: 10px 12px;
  border: 1px solid #dce4f2;
  border-radius: 14px;
  background: #fbfdff;
}
.radar-limit-row input { width: 76px; }
.result-count {
  margin-bottom: 10px;
  color: #214fc2;
  font-weight: 800;
}
.highlight {
  padding: 0 2px;
  border-radius: 4px;
  background: #fff1a8;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(16, 24, 39, 0.42);
}
.modal-card {
  display: grid;
  gap: 14px;
  width: min(720px, 100%);
  max-height: 88vh;
  overflow: auto;
  padding: 24px;
  border-radius: 22px;
  background: white;
  box-shadow: 0 24px 70px rgba(16, 24, 39, 0.28);
}
.venue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}
.check-card {
  display: flex;
  grid-template-columns: none;
  flex-direction: row;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #dce4f2;
  border-radius: 12px;
  background: #fbfdff;
}
.check-card input { width: auto; }

@media (max-width: 1080px) {
  .desktop-shell, .page-grid, .library-workbench, .topics-layout, .search-bar { grid-template-columns: 1fr; }
  .sidebar { height: auto; overflow: visible; }
  .side-nav { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
}
</style>
