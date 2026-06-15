# LitRadar

个人文献雷达 —— 追踪 arXiv 最新论文，AI 辅助阅读，桌面端一键使用。

## 功能

- **今日雷达** — 根据研究方向关键词，每天从 arXiv 自动推荐高分论文，支持自定义推荐数量
- **论文搜索** — arXiv 关键词检索 + OpenAlex 语义搜索推荐，标题/摘要 AI 翻译
- **论文库** — 收藏、管理论文，AI 结构化阅读（研究方向、任务定义、网络框架、创新点等），PDF 预览
- **论文笔记** — 基于 paper-qa 的深度阅读笔记，支持导出到 Obsidian
- **本地设置** — 配置 AI 接口（兼容 OpenAI/DeepSeek 等），Obsidian 知识库路径
- **桌面应用** — Tauri 打包为独立 macOS 应用（.app / .dmg），双击即用，无需安装 Python 环境

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Django 5 + Django REST Framework + SQLite |
| 前端 | Vue 3 + TypeScript + Vite |
| 桌面壳 | Tauri 2 (Rust) |
| AI | OpenAI 兼容接口（DeepSeek 等），paper-qa |
| PDF | PyMuPDF (fitz) |
| 打包 | PyInstaller → Tauri sidecar → .app |

## 快速开始

### 开发环境

```bash
# 安装后端依赖并启动 Django (127.0.0.1:8765)
npm run backend:dev

# 启动前端开发服务器 (localhost:1420)
npm run frontend:dev

# 启动 Tauri 桌面应用（前端需先启动）
npm run tauri:dev
```

### 运行测试

```bash
npm run backend:test
npm run frontend:test
```

### 构建桌面应用

```bash
# 1. PyInstaller 打包 Django
cd backend
.venv/bin/pyinstaller --distpath ../frontend/src-tauri/binaries --workpath /tmp/pyinstaller-build --clean --noconfirm pyinstaller.spec

# 2. 重命名二进制（Tauri 要求 target-triple 后缀）
mv ../frontend/src-tauri/binaries/litradar-backend ../frontend/src-tauri/binaries/litradar-backend-aarch64-apple-darwin

# 3. Tauri 打包
npm --prefix frontend run tauri -- build
```

构建产物：
- `frontend/src-tauri/target/release/bundle/macos/LitRadar.app`
- `frontend/src-tauri/target/release/bundle/dmg/LitRadar_0.1.0_aarch64.dmg`

## 项目结构

```
LitRadar/
├── backend/                    # Django 后端
│   ├── litradar/settings.py    # Django 配置
│   ├── apps/core/
│   │   ├── urls.py             # 所有 API 视图和逻辑（核心文件）
│   │   ├── models.py           # 数据模型
│   │   └── tests/test_mvp_api.py  # 测试
│   ├── run_django.py           # PyInstaller 入口
│   └── pyinstaller.spec        # PyInstaller 配置
├── frontend/                   # Vue 前端
│   ├── src/
│   │   ├── App.vue             # 单文件 SPA（模板 + 逻辑 + 样式）
│   │   ├── api/                # API 客户端 + 测试
│   │   └── main.ts             # Vue 入口
│   └── src-tauri/              # Tauri 桌面壳
│       ├── src/main.rs         # Rust 入口（启动 Django 子进程）
│       ├── tauri.conf.json     # Tauri 配置
│       ├── icons/              # 应用图标
│       └── binaries/           # Django 二进制（构建产物）
├── docs/                       # 文档
└── scripts/                    # 开发脚本
```

## 数据模型

```
ResearchTopic ──< Paper ──< DailyRecommendation >── ResearchTopic
                   │
                   ├── PaperInsight (1:1)   # AI 结构化阅读结果
                   ├── PaperNote (1:1)      # paper-qa 深度笔记
                   └── PaperFigure (1:N)    # 论文图表
```

论文生命周期：`recommended` → `saved` → `parsed` → `analyzed` → `exported`

## 配置

### AI 接口

在设置页面填写：
- **Base URL** — API 地址（如 `https://api.deepseek.com`）
- **API Key** — 密钥
- **模型名称** — 文本模型和视觉模型

后端兼容 OpenAI 接口格式，支持 DeepSeek、OpenAI、或其他兼容服务。

### Obsidian 导出

在设置页面配置 Vault 路径后，论文分析结果会自动导出为 Markdown：
- `<vault>/<topic>/Papers/` — 论文笔记
- `<vault>/<topic>/Graph/` — 知识图谱
- `<vault>/<topic>/Notes/` — 深度笔记

## License

MIT
