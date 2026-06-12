# LitRadar Project Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the initial LitRadar monorepo skeleton with a Vue 3 frontend, Django local backend, and Tauri configuration for a desktop-integrated app.

**Architecture:** Tauri owns the desktop shell and will later manage a local Django process. Vue 3 renders the UI and calls Django through a local HTTP API. Django provides the local API, SQLite-backed settings, and the first health endpoint.

**Tech Stack:** Tauri, Vue 3, TypeScript, Vite, Vitest, Python, Django, Django REST Framework, pytest.

---

## File Structure

- `package.json` — root npm scripts for frontend dev/test/build.
- `frontend/package.json` — frontend dependencies and scripts.
- `frontend/index.html` — Vite entry HTML.
- `frontend/vite.config.ts` — Vue/Vitest configuration.
- `frontend/tsconfig.json` — frontend TypeScript config.
- `frontend/src/main.ts` — Vue bootstrap.
- `frontend/src/App.vue` — initial app shell and backend health check UI.
- `frontend/src/api/health.ts` — typed frontend API function for backend health.
- `frontend/src/api/health.test.ts` — Vitest coverage for the health API function.
- `frontend/src-tauri/Cargo.toml` — Tauri Rust package manifest.
- `frontend/src-tauri/tauri.conf.json` — Tauri application configuration.
- `frontend/src-tauri/src/main.rs` — minimal Tauri entrypoint.
- `backend/requirements.txt` — Python dependencies.
- `backend/pytest.ini` — pytest configuration.
- `backend/manage.py` — Django CLI entrypoint.
- `backend/litradar/settings.py` — Django settings for local desktop backend.
- `backend/litradar/urls.py` — root URL routing.
- `backend/litradar/wsgi.py` — WSGI entrypoint.
- `backend/litradar/asgi.py` — ASGI entrypoint.
- `backend/apps/core/views.py` — health endpoint implementation.
- `backend/apps/core/urls.py` — core app URL routing.
- `backend/apps/core/tests/test_health.py` — pytest coverage for `/api/health/`.
- `scripts/dev-backend.sh` — local backend startup helper.

---

## Task 1: Backend health API

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/manage.py`
- Create: `backend/litradar/settings.py`
- Create: `backend/litradar/urls.py`
- Create: `backend/litradar/wsgi.py`
- Create: `backend/litradar/asgi.py`
- Create: `backend/apps/core/views.py`
- Create: `backend/apps/core/urls.py`
- Create: `backend/apps/core/tests/test_health.py`

- [ ] **Step 1: Install backend test dependencies**

Run:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

Expected: dependencies install without errors.

- [ ] **Step 2: Write failing health endpoint test**

Create `backend/apps/core/tests/test_health.py`:

```python
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_endpoint_returns_ok(client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "litradar-backend"}
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
cd backend && .venv/bin/pytest apps/core/tests/test_health.py -v
```

Expected: FAIL because the Django project or `health` route is not implemented yet.

- [ ] **Step 4: Implement minimal Django backend**

Create the Django project files and a `health_view` returning the expected JSON.

- [ ] **Step 5: Run backend test to verify it passes**

Run:

```bash
cd backend && .venv/bin/pytest apps/core/tests/test_health.py -v
```

Expected: PASS.

---

## Task 2: Frontend health API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/api/health.ts`
- Create: `frontend/src/api/health.test.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`

- [ ] **Step 1: Install frontend dependencies**

Run:

```bash
cd frontend && npm install
```

Expected: dependencies install without errors.

- [ ] **Step 2: Write failing frontend API test**

Create `frontend/src/api/health.test.ts`:

```typescript
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
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
cd frontend && npm test -- --run src/api/health.test.ts
```

Expected: FAIL because `fetchHealth` is not implemented yet.

- [ ] **Step 4: Implement minimal frontend app and API client**

Create `fetchHealth`, Vue bootstrap, and initial app shell that displays the architecture and health status.

- [ ] **Step 5: Run frontend test to verify it passes**

Run:

```bash
cd frontend && npm test -- --run src/api/health.test.ts
```

Expected: PASS.

---

## Task 3: Tauri desktop configuration

**Files:**
- Create: `frontend/src-tauri/Cargo.toml`
- Create: `frontend/src-tauri/tauri.conf.json`
- Create: `frontend/src-tauri/src/main.rs`

- [ ] **Step 1: Create minimal Tauri config**

Add a Tauri app configuration pointing to the Vite frontend.

- [ ] **Step 2: Verify Rust toolchain availability**

Run:

```bash
rustc --version && cargo --version
```

Expected: versions print successfully. If Rust is missing, document that Tauri compile verification is blocked until Rust is installed.

---

## Task 4: Developer scripts and root docs

**Files:**
- Create: `package.json`
- Create: `scripts/dev-backend.sh`

- [ ] **Step 1: Add root npm scripts**

Root scripts delegate to frontend and document backend startup.

- [ ] **Step 2: Add backend startup helper**

Create `scripts/dev-backend.sh` to run Django on `127.0.0.1:8765`.

- [ ] **Step 3: Final verification**

Run:

```bash
backend/.venv/bin/python backend/manage.py check
cd backend && .venv/bin/pytest apps/core/tests/test_health.py -v
cd frontend && npm test -- --run src/api/health.test.ts
```

Expected: Django check passes, backend health test passes, frontend health API test passes. Tauri compile verification requires Rust.
