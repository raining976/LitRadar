# Topic Search Radar Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine LitRadar research directions, paper search scoring/highlighting, and Today Radar refresh behavior around the user's current workflow.

**Architecture:** Keep the existing Django core API and single Vue `App.vue` shell. Backend owns scoring, matched terms, search result ordering, and non-cached radar replacement; frontend owns modal-based topic editing, CCF venue multiselect, highlighted result rendering, and radar-count edit UI.

**Tech Stack:** Django 5, pytest, Vue 3 Composition API, TypeScript, Vitest, Vite.

---

## File Structure

- Modify `backend/apps/core/urls.py`: scoring helpers, payload shape, topic field mapping, search response metadata, radar replacement behavior.
- Modify `backend/apps/core/tests/test_mvp_api.py`: regression tests for scoring/matches, search payload shape, topic payload without user-facing removed fields expectations, and radar no-cache replacement.
- Modify `frontend/src/api/litradar.ts`: extend `Paper` with `matched_terms`, keep `ResearchTopic.arxiv_categories` as storage for selected venues.
- Modify `frontend/src/api/litradar.test.ts`: assert matched search payload compatibility only if API signatures change.
- Modify `frontend/src/App.vue`: topic modal UI, venue multiselect, result count/highlighting, radar count edit/save row.

## Task 1: Backend Search Scoring and Matched Terms

**Files:**
- Modify: `backend/apps/core/tests/test_mvp_api.py`
- Modify: `backend/apps/core/urls.py`

- [ ] **Step 1: Write failing tests**

Append these tests to `backend/apps/core/tests/test_mvp_api.py`:

```python
def test_enrich_paper_metadata_scores_and_reports_matched_terms():
    paper = {
        "title": "Mamba Network for Hyperspectral Image Fusion",
        "abstract": "A remote sensing method accepted at CVPR for SAR optical fusion.",
        "authors": [],
        "year": 2026,
        "arxiv_id": "2601.12345",
        "source": "arXiv",
        "source_url": "",
        "pdf_url": "",
    }

    enriched = enrich_paper_metadata(paper, "remote sensing image fusion", ["hyperspectral", "CVPR"])

    assert enriched["match_score"] >= 60
    assert "remote" in enriched["matched_terms"]
    assert "hyperspectral" in enriched["matched_terms"]
    assert "CVPR" in enriched["matched_terms"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /data2/raining/Projects/LitRadar/backend && .venv/bin/pytest apps/core/tests/test_mvp_api.py::test_enrich_paper_metadata_scores_and_reports_matched_terms -q
```

Expected: FAIL because `matched_terms` does not exist or score is below 60.

- [ ] **Step 3: Implement scoring helper**

In `backend/apps/core/urls.py`, replace `fuzzy_match_score()` and `enrich_paper_metadata()` with helper functions that return score and matched terms:

```python
def score_text_matches(title, abstract, terms):
    title_normalized = title.lower()
    abstract_normalized = abstract.lower()
    score = 0
    matched_terms = []
    for term in terms:
        item = term.strip()
        if not item:
            continue
        item_lower = item.lower()
        term_matched = False
        if item_lower in title_normalized:
            score += 35
            term_matched = True
        elif item_lower in abstract_normalized:
            score += 22
            term_matched = True
        else:
            for token in tokenize(item):
                if token in title_normalized:
                    score += 10
                    matched_terms.append(token)
                    term_matched = True
                elif token in abstract_normalized:
                    score += 6
                    matched_terms.append(token)
                    term_matched = True
        if term_matched:
            matched_terms.append(item)
    deduped_matches = []
    for term in matched_terms:
        if term and term not in deduped_matches:
            deduped_matches.append(term)
    return min(score, 100), deduped_matches


def fuzzy_match_score(text, terms):
    score, _matches = score_text_matches(text, "", terms)
    return score


def enrich_paper_metadata(paper, query="", keywords=None):
    enriched = dict(paper)
    terms = [query, *(keywords or [])]
    score, matched_terms = score_text_matches(paper.get("title", ""), paper.get("abstract", ""), terms)
    enriched["match_score"] = score
    enriched["matched_terms"] = matched_terms
    enriched["tags"] = infer_paper_tags(paper)
    return enriched
```

- [ ] **Step 4: Verify test passes**

Run the same pytest command. Expected: PASS.

## Task 2: Backend Search Payload and Radar Replacement

**Files:**
- Modify: `backend/apps/core/tests/test_mvp_api.py`
- Modify: `backend/apps/core/urls.py`

- [ ] **Step 1: Write failing radar replacement test**

Append:

```python
@pytest.mark.django_db
def test_radar_run_replaces_today_recommendations_and_requires_score_above_60(client, monkeypatch):
    topic_response = client.post(
        reverse("topics-list"),
        data={"name": "视觉方向", "keywords": ["hyperspectral fusion", "CVPR"], "daily_limit": 3, "enabled": True},
        content_type="application/json",
    )
    topic_id = topic_response.json()["id"]
    calls = {"count": 0}

    def fake_search(query, categories=None, max_results=10):
        calls["count"] += 1
        suffix = calls["count"]
        return [
            {
                "title": f"Hyperspectral Fusion CVPR Paper {suffix}-{index}",
                "authors": ["Researcher A"],
                "year": 2026,
                "abstract": "remote sensing hyperspectral fusion with CVPR experiments",
                "arxiv_id": f"2601.200{suffix}{index}",
                "source": "arXiv",
                "source_url": f"https://arxiv.org/abs/2601.200{suffix}{index}",
                "pdf_url": f"https://arxiv.org/pdf/2601.200{suffix}{index}",
            }
            for index in range(5)
        ] + [
            {
                "title": "Unrelated Paper",
                "authors": [],
                "year": 2026,
                "abstract": "quantum chemistry",
                "arxiv_id": f"2601.low{suffix}",
                "source": "arXiv",
                "source_url": "",
                "pdf_url": "",
            }
        ]

    monkeypatch.setattr("apps.core.urls.search_arxiv", fake_search)

    first = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 3}, content_type="application/json").json()
    second = client.post(reverse("radar-run", args=[topic_id]), data={"limit": 3}, content_type="application/json").json()

    assert len(first["recommendations"]) == 3
    assert len(second["recommendations"]) == 3
    assert {item["paper"]["arxiv_id"] for item in first["recommendations"]} != {item["paper"]["arxiv_id"] for item in second["recommendations"]}
    assert all(item["score"] > 60 for item in second["recommendations"])
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd /data2/raining/Projects/LitRadar/backend && .venv/bin/pytest apps/core/tests/test_mvp_api.py::test_radar_run_replaces_today_recommendations_and_requires_score_above_60 -q
```

Expected: FAIL because existing radar skips cached recommendations and does not replace today's set.

- [ ] **Step 3: Implement replacement radar**

In `radar_run_view()`:

1. After `today = date.today()`, delete existing recommendations for this topic/date:

```python
DailyRecommendation.objects.filter(topic=topic, recommend_date=today).delete()
```

2. Before the loop, filter candidates:

```python
candidates = [candidate for candidate in candidates if candidate.get("match_score", 0) > 60]
```

3. Randomize candidates before selection:

```python
import random
```

at top, then:

```python
random.shuffle(candidates)
```

4. Remove the existing `DailyRecommendation.objects.filter(...).exists()` skip block.

5. Use candidate score directly:

```python
score = candidate.get("match_score", 0)
matches = candidate.get("matched_terms", [])
```

- [ ] **Step 4: Verify test passes**

Run the same pytest command. Expected: PASS.

## Task 3: Frontend Topic Modal and Venue Multi-select

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Update state**

Add:

```ts
const topicModalOpen = ref(false);
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
```

Remove `description` and `obsidian_folder` from `topicForm`, leaving `name`, `keywordsText`, and `venues`.

- [ ] **Step 2: Update topic helpers**

Change `resetTopicForm()` to clear only the new fields and open modal when adding:

```ts
function openNewTopicModal() {
  editingTopicId.value = null;
  topicForm.value = { name: '', keywordsText: '', venues: [] };
  topicModalOpen.value = true;
}
```

Change `editTopic(topic)` to:

```ts
function editTopic(topic: ResearchTopic) {
  editingTopicId.value = topic.id;
  topicForm.value = {
    name: topic.name,
    keywordsText: topic.keywords.join('\n'),
    venues: topic.arxiv_categories,
  };
  topicModalOpen.value = true;
}
```

- [ ] **Step 3: Update submit payload**

In `submitTopic()`, send:

```ts
const payload = {
  name: topicForm.value.name,
  description: '',
  keywords: lines(topicForm.value.keywordsText),
  arxiv_categories: topicForm.value.venues,
  obsidian_folder: '',
  enabled: true,
};
```

After success, close the modal.

- [ ] **Step 4: Replace topics template**

Remove the inline `<form class="content-panel form-panel">` from the topics page. Render only the current-direction card, topic cards, and an add card. Add a modal block:

```vue
<div v-if="topicModalOpen" class="modal-backdrop">
  <form class="modal-card" @submit.prevent="submitTopic">
    <div class="panel-heading compact-heading">
      <h2>{{ editingTopicId ? '编辑研究方向' : '新增研究方向' }}</h2>
      <button class="ghost" type="button" @click="topicModalOpen = false">关闭</button>
    </div>
    <label>名称<input v-model="topicForm.name" /></label>
    <label>关键词（每行一个）<textarea v-model="topicForm.keywordsText" /></label>
    <div class="venue-grid">
      <label v-for="venue in venueOptions" :key="venue.name" class="check-card">
        <input v-model="topicForm.venues" type="checkbox" :value="venue.name" />
        <span>{{ venue.group }} · {{ venue.name }}</span>
      </label>
    </div>
    <div class="button-row">
      <button class="primary" type="submit" :disabled="isLoading('topic-save')">保存</button>
      <button class="ghost" type="button" @click="topicModalOpen = false">取消</button>
    </div>
  </form>
</div>
```

- [ ] **Step 5: Build check**

Run:

```bash
cd /data2/raining/Projects/LitRadar && npm run frontend:build
```

Expected: build passes.

## Task 4: Frontend Search Result Count and Highlighting

**Files:**
- Modify: `frontend/src/api/litradar.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Extend TypeScript type**

Add to `Paper` interface in `frontend/src/api/litradar.ts`:

```ts
matched_terms?: string[];
```

- [ ] **Step 2: Add highlighting helpers**

In `App.vue`, add:

```ts
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
```

- [ ] **Step 3: Update search template**

Above `.search-bar`, add:

```vue
<div v-if="searchResults.length" class="result-count">共找到 {{ searchResults.length }} 篇候选论文</div>
```

In result title/abstract, render `highlightedParts(...)` spans with class `highlight`.

- [ ] **Step 4: Build check**

Run frontend build. Expected: pass.

## Task 5: Today Radar Count Editing UI

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add state and helpers**

Add:

```ts
const radarLimitEditing = ref(false);
const radarLimitDraft = ref(3);

function startRadarLimitEdit() {
  radarLimitDraft.value = radarLimit.value;
  radarLimitEditing.value = true;
}

function saveRadarLimit() {
  radarLimit.value = Math.max(1, Math.min(Number(radarLimitDraft.value) || 3, 10));
  radarLimitEditing.value = false;
}
```

- [ ] **Step 2: Replace always-visible radar input**

Replace radar controls with a left/right row:

```vue
<div class="radar-limit-row">
  <span>每日推荐数量</span>
  <strong v-if="!radarLimitEditing">{{ radarLimit }}</strong>
  <input v-else v-model.number="radarLimitDraft" type="number" min="1" max="10" />
  <button v-if="!radarLimitEditing" class="ghost" @click="startRadarLimitEdit">编辑</button>
  <button v-else class="primary" @click="saveRadarLimit">保存</button>
</div>
```

Keep the `更新今日推荐` button separate.

- [ ] **Step 3: Build check**

Run frontend build. Expected: pass.

## Task 6: Full Verification

**Files:**
- No edits expected.

- [ ] **Step 1: Backend tests**

Run:

```bash
cd /data2/raining/Projects/LitRadar/backend && .venv/bin/pytest
```

Expected: all tests pass.

- [ ] **Step 2: Django checks**

Run:

```bash
cd /data2/raining/Projects/LitRadar/backend && .venv/bin/python manage.py check && .venv/bin/python manage.py makemigrations --check
```

Expected: no system check issues and no model changes detected.

- [ ] **Step 3: Frontend tests**

Run:

```bash
cd /data2/raining/Projects/LitRadar/frontend && npm test -- --run
```

Expected: all Vitest tests pass.

- [ ] **Step 4: Frontend build**

Run:

```bash
cd /data2/raining/Projects/LitRadar && npm run frontend:build
```

Expected: build passes.

- [ ] **Step 5: Runtime smoke**

Use the existing backend on `127.0.0.1:8765` or start it with `npm run backend:dev`. Smoke these paths:

```bash
python3 - <<'PY'
import json
import urllib.request
base = 'http://127.0.0.1:8765'
def req(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {'Content-Type': 'application/json'} if payload is not None else {}
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read().decode())
status, topic = req('POST', '/api/topics/', {'name': 'Smoke Venue Topic', 'keywords': ['hyperspectral fusion'], 'arxiv_categories': ['CVPR', 'ICLR']})
assert status == 201
status, results = req('GET', f"/api/papers/search/?query=hyperspectral+fusion&topic_id={topic['id']}")
assert status == 200
assert isinstance(results, list)
assert all('match_score' in item and 'matched_terms' in item for item in results)
req('DELETE', f"/api/topics/{topic['id']}/")
print('smoke ok')
PY
```

Expected: `smoke ok`.
