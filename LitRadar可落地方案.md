# LitRadar 可落地方案

## 1. 项目定位

LitRadar 是一个面向科研人员的 **个人研究方向雷达 + 多模态论文结构阅读助手**。

它要解决的不是单纯“帮用户总结 PDF”，而是三个更具体的痛点：

1. **检索文献不方便**：用户很难持续跟踪自己研究方向的新论文，也很难从大量候选论文里快速筛出值得读的内容。
2. **通用 AI 读 PDF 不完整**：很多论文的核心信息藏在架构图、流程图、网络结构图中，普通文本解析容易漏掉图中的模块关系和信息流向。
3. **AI 对网络结构理解不到位**：通用摘要经常只概括论文结论，不能稳定讲清楚输入是什么、网络怎么走、模块怎么连接、创新点具体落在哪。

因此，LitRadar 的核心价值是：

> 根据用户长期关注的研究方向，自动发现值得看的论文，并把每篇论文沉淀为结构化、可检索、可复盘、容易启发 idea 的个人知识库。

第一版采用能力分层方案：基础功能必须稳定可用，AI 能力强时自动增强视觉和结构理解，AI 能力不足时也能通过文本解析、图片抽取、人工选择关键图和固定分析模板完成闭环。

---

## 2. MVP 目标

第一版 MVP 需要打通三条轻量闭环。

### 2.1 每日论文雷达

用户配置自己感兴趣的研究方向，例如：

- remote sensing change detection
- SAR image interpretation
- transformer for semantic segmentation
- multimodal remote sensing foundation model

系统每天自动从 arXiv 等平台检索候选论文，调用 AI 对论文进行相关性判断和简短解读，最终推送固定数量的论文，例如每天 3 篇，到用户指定的知识库分类中。

### 2.2 图文增强阅读

用户上传或关联 PDF 后，系统不仅解析正文，还抽取 PDF 中的图片，尤其关注可能是论文架构图、方法流程图、网络结构图的图片。

如果 AI 中转站支持视觉模型，则直接让 AI 结合图片和上下文解释论文框架；如果不支持视觉模型，则先把图片作为知识库附件保存，并让用户手动选择关键图，再基于图片附近的 caption、正文段落和论文方法章节生成半自动解读。

### 2.3 论文结构 Skill 阅读

系统内置专门面向算法论文的结构化阅读模板，不再只输出普通摘要，而是固定分析：

- 研究方向
- 任务定义
- 输入数据
- 输出结果
- 网络整体框架
- 模块组成
- 信息流向
- 损失函数
- 训练流程
- 推理流程
- 创新点
- 局限性
- 可复现疑点
- 可启发的新 idea

这样生成的知识库不仅方便“看懂论文”，也方便后续横向比较不同论文，找到可改进点和研究灵感。

---

## 3. 技术栈与一体化架构

LitRadar 第一版采用 **桌面一体化单体架构**：用户看到的是一个 Tauri 桌面应用，内部由 Tauri 启动并托管本地 Django 服务。这样既保留 Vue 3 的界面开发效率和 Python/Django 的 AI、PDF、数据处理生态，又避免个人项目维护传统前后端分离带来的部署和协作成本。

### 3.1 桌面端壳与界面

采用：**Tauri + Vue 3 + TypeScript**

职责：

- 提供桌面端 UI。
- 启动、探测和关闭本地 Django 服务进程。
- 管理本地文件访问权限。
- 配置用户研究方向关键词。
- 展示每日推荐论文。
- 选择 PDF 文件。
- 展示 PDF 图片、架构图候选和 AI 解读。
- 选择 Obsidian Vault 目录。
- 通过本地 HTTP 调用 Django API。
- 将生成的 Markdown 和图片附件写入本地知识库目录。

选择 Tauri 的原因：

- 比 Electron 更轻量。
- 可以安全访问本地文件系统，适合和 PDF、Obsidian Vault、本地图片附件联动。
- 前端仍使用 Vue 3，开发效率高。
- Rust 层只负责进程管理、文件选择、路径授权、Markdown 写入等必要本地能力，不承载主要业务逻辑。

### 3.2 本地后端服务

采用：**Python + Django + Django REST Framework**

运行方式：**由 Tauri 在本机拉起 Django 服务，监听 `127.0.0.1` 随机或固定端口。**

职责：

- 提供本地 API 服务。
- 管理论文元数据、用户关注方向、推荐任务、PDF 解析结果、图片信息、AI 分析结果、导出记录。
- 调用 arXiv 等论文检索 API。
- 调用 AI 中转站 API。
- 执行每日推荐任务。
- 生成 Obsidian Markdown 内容。

第一版使用 SQLite 作为本地数据库，数据库文件放在应用数据目录中。由于这是个人桌面工具，暂不引入多用户系统、远程数据库和复杂权限系统。

推荐 Django App 划分：

- `topics`：用户研究方向、关键词、每日推荐数量、知识库分类路径。
- `papers`：论文元数据、PDF 文件、解析文本。
- `radar`：每日检索、候选论文筛选、推荐记录。
- `figures`：PDF 图片抽取、caption、关键图标记。
- `ai`：AI Client、Prompt 模板、结构化阅读 Skill。
- `exports`：Obsidian Markdown 生成和导出记录。
- `settings_app`：AI 中转站配置、模型配置、Obsidian 路径。

### 3.3 一体化运行方式

开发期：

```text
npm run tauri dev
    ↓
Tauri 启动 Vue 开发服务
    ↓
Tauri 或开发脚本启动 Django 本地服务
    ↓
Vue 调用 http://127.0.0.1:<port>/api
```

发布期：

```text
用户打开 LitRadar 桌面应用
    ↓
Tauri 检查本地 Django 服务是否已运行
    ↓
未运行则启动内置 Python/Django 服务
    ↓
等待 /api/health/ 返回正常
    ↓
加载 Vue 界面
    ↓
用户无感使用完整应用
```

这种方式对用户是“一体化桌面应用”，对开发者仍然保持清晰边界：Vue 负责界面，Tauri 负责本地能力和进程管理，Django 负责业务逻辑和 AI/PDF 处理。

### 3.4 AI 层

采用：**本地 Django 服务统一调用 AI 中转站 API 接口**

职责：

- 不在本地部署大模型。
- 不在 Vue 前端直接暴露 API Key。
- 后端封装统一 AI Client。
- 支持文本模型和视觉模型能力探测。
- 支持后续替换不同中转站和模型。

AI 中转站建议兼容 OpenAI 风格接口：

- `base_url`
- `api_key`
- `model`
- `messages`
- `temperature`
- `stream`

如果中转站支持视觉模型，则增加图片输入能力；如果不支持，LitRadar 降级为“PDF 文本 + 图片抽取 + caption/上下文分析”。

---

## 4. 总体架构

```text
┌──────────────────────────────────────────────────┐
│ LitRadar 桌面应用                                 │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ Tauri + Vue 3 界面                          │  │
│  │                                            │  │
│  │ - 研究方向配置                              │  │
│  │ - 每日论文雷达                              │  │
│  │ - 论文库 / 知识库浏览                        │  │
│  │ - PDF 上传与图片预览                         │  │
│  │ - 架构图候选选择                             │  │
│  │ - AI 结构化阅读结果展示                      │  │
│  │ - Obsidian 导出                              │  │
│  └─────────────────────┬──────────────────────┘  │
│                        │ 本地 HTTP API            │
│                        ▼                          │
│  ┌────────────────────────────────────────────┐  │
│  │ Tauri 托管的本地 Django 服务                │  │
│  │ 127.0.0.1:<port>                           │  │
│  │                                            │  │
│  │ - arXiv 检索                                │  │
│  │ - 每日推荐任务                              │  │
│  │ - 论文相关性评分                            │  │
│  │ - PDF 文本解析                              │  │
│  │ - PDF 图片抽取                              │  │
│  │ - 关键图识别 / 标记                          │  │
│  │ - 论文结构 Skill 分析                        │  │
│  │ - Markdown 生成                             │  │
│  └───────────────┬───────────────┬────────────┘  │
│                  │               │               │
│                  ▼               ▼               │
│  ┌────────────────────┐   ┌────────────────────┐ │
│  │ 本地 SQLite 数据库   │   │ AI 中转站 API        │ │
│  │ 应用数据目录         │   │ 文本模型 / 视觉模型   │ │
│  └────────────────────┘   └────────────────────┘ │
│                  │                               │
│                  ▼                               │
│  ┌────────────────────────────────────────────┐  │
│  │ 本地知识库 / 文件系统                        │  │
│  │                                            │  │
│  │ - Obsidian Markdown                         │  │
│  │ - PDF 文件                                  │  │
│  │ - 论文图片附件                               │  │
│  │ - 每日推荐分类目录                           │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 5. 核心模块设计

## 5.1 用户研究方向配置模块

### 目标

让用户把长期关注的研究方向固定下来，系统围绕这些方向持续检索和沉淀论文。

### 第一版能力

用户可以创建多个 Topic，例如：

```text
Topic: 遥感变化检测
关键词:
- remote sensing change detection
- SAR change detection
- transformer change detection
arXiv 分类:
- cs.CV
- eess.IV
每日推荐数量: 3
知识库目录: Obsidian/LitRadar/遥感变化检测/
```

### 字段建议

`ResearchTopic`：

- `id`
- `name`
- `description`
- `keywords`
- `arxiv_categories`
- `daily_limit`
- `obsidian_folder`
- `enabled`
- `created_at`
- `updated_at`

### 价值

这个模块决定了产品不是一次性工具，而是用户自己的研究方向雷达。用户每天打开后，可以看到每个方向新增了哪些值得关注的论文。

---

## 5.2 arXiv AI 检索与每日推荐模块

### 目标

解决“检索文献不方便”的问题，让系统主动发现论文，而不是每次都靠用户手动搜。

### 第一版流程

```text
读取启用的 ResearchTopic
    ↓
根据关键词和 arXiv 分类检索候选论文
    ↓
过滤最近 N 天或最近一批论文
    ↓
去重：排除已推荐、已保存、标题重复论文
    ↓
AI 根据用户 Topic 判断相关性并打分
    ↓
选择得分最高的前 daily_limit 篇
    ↓
生成推荐理由和简短摘要
    ↓
保存推荐记录
    ↓
导出到 Obsidian 对应分类目录
```

### AI 评分维度

每篇候选论文给出：

- 与用户研究方向的相关性分数
- 是否值得阅读
- 可能对应的细分方向
- 主要方法关键词
- 可能启发的 idea
- 推荐理由

### 推荐记录字段

`DailyRecommendation`：

- `id`
- `topic`
- `paper`
- `recommend_date`
- `score`
- `reason`
- `idea_hint`
- `exported_to_obsidian`

### 推送形式

MVP 中不做系统通知，先做两种稳定方式：

1. 应用内“今日推荐”页面。
2. 自动生成 Obsidian Daily Radar Markdown。

示例目录：

```text
Obsidian Vault/
  LitRadar/
    遥感变化检测/
      Daily/
        2026-05-26.md
      Papers/
        2026-xxx-paper-title.md
      Figures/
        paper-title-fig1.png
```

---

## 5.3 论文库与知识库模块

### 目标

让用户积累属于自己的结构化论文知识库，方便查看每篇论文的研究方向、创新点、方法框架和 idea 启发。

### 第一版能力

- 保存推荐论文。
- 保存用户手动检索论文。
- 支持按 Topic 分类。
- 支持查看论文状态：未读、已解析、已分析、已导出。
- 支持查看论文结构化信息。

### Paper 字段建议

`Paper`：

- `id`
- `title`
- `authors`
- `year`
- `abstract`
- `arxiv_id`
- `doi`
- `source`
- `source_url`
- `pdf_url`
- `local_pdf_path`
- `topic`
- `status`
- `created_at`
- `updated_at`

### PaperInsight 字段建议

`PaperInsight`：

- `paper`
- `research_direction`
- `task_definition`
- `input_data`
- `output_result`
- `network_overview`
- `module_list`
- `information_flow`
- `loss_functions`
- `training_process`
- `inference_process`
- `innovation_points`
- `limitations`
- `reproduction_questions`
- `idea_hints`
- `keywords`
- `markdown_note`

---

## 5.4 PDF 文本与图片解析模块

### 目标

解决通用 AI 直接读 PDF 容易漏掉图中信息的问题。

### 第一版能力

- 提取 PDF 正文文本。
- 提取 PDF 中的图片。
- 保存图片附件。
- 尝试关联图片 caption。
- 给图片生成候选类型：架构图、实验结果图、数据集示意图、普通图。
- 允许用户手动标记关键图。

### 推荐工具

- `PyMuPDF`：用于提取文本、图片、页码、图片位置。
- `Pillow`：用于图片保存、格式转换、缩略图生成。

### 关键图识别规则

第一版可以用规则 + AI 轻量判断：

1. caption 或上下文包含：
   - architecture
   - framework
   - pipeline
   - overview
   - network
   - structure
   - module
   - workflow
2. 图片位于 Method、Approach、Proposed Method 等章节附近。
3. 图片编号较靠前，例如 Fig. 1、Fig. 2、Fig. 3。
4. 用户可以在前端手动选择“这是关键架构图”。

### Figure 字段建议

`PaperFigure`：

- `paper`
- `page_number`
- `figure_index`
- `image_path`
- `caption`
- `context_text`
- `figure_type`
- `is_key_figure`
- `ai_description`

---

## 5.5 图文增强阅读模块

### 目标

帮助用户理解论文架构图、方法流程图、网络结构图。

### 两种能力模式

#### 模式 A：视觉模型增强模式

当 AI 中转站支持视觉模型时：

- 后端把关键图图片和 caption 一起发给视觉模型。
- 让模型解释图片中模块名称、连接关系、输入输出、整体流程。
- 再结合正文 Method 章节生成结构化网络理解。

输出示例：

```text
该图展示了一个 encoder-decoder 结构。
输入为双时相遥感图像 I1 和 I2。
两个分支共享权重提取多尺度特征。
中间通过差异增强模块计算变化特征。
最终 decoder 输出变化检测图。
```

#### 模式 B：文本降级模式

当 AI 中转站不支持视觉模型时：

- 系统仍然抽取图片并保存到知识库。
- 用户手动选择关键图。
- AI 使用 caption、图片附近正文、Method 章节文本进行分析。
- Markdown 中保留图片链接，方便用户对照查看。

这种模式不能真正“看懂图片像素”，但可以显著优于只读全文文本，因为它把关键图、caption 和方法段落绑定到同一个分析流程中。

---

## 5.6 论文结构 Skill 模块

### 目标

解决 AI 阅读论文时对网络结构、输入流向、模块关系理解不到位的问题。

这里的 Skill 不是外部 Claude Code skill，而是产品内部的一套固定分析流程和 Prompt 模板，可以理解为 LitRadar 的“论文阅读专家模式”。

### Skill 输入

- 论文标题
- 摘要
- Method 章节文本
- Conclusion 章节文本
- 关键图 caption
- 关键图图片或图片链接
- 用户研究方向 Topic

### Skill 输出

固定输出以下结构：

```markdown
## 研究方向

## 论文要解决的问题

## 输入与输出

## 整体网络框架

## 模块拆解

| 模块 | 输入 | 输出 | 作用 | 对应创新点 |
|---|---|---|---|---|

## 信息流向

用步骤说明数据从输入到输出如何流动。

## 损失函数与训练目标

## 推理流程

## 创新点总结

## 与已有方法的区别

## 局限性

## 可复现疑点

## 可以启发的新 idea
```

### Prompt 设计原则

- 要求 AI 不确定时明确说“不确定”。
- 要求 AI 区分“论文明确写到的内容”和“根据图文推断的内容”。
- 要求 AI 优先分析网络结构和信息流，而不是泛泛总结背景。
- 要求 AI 输出表格，方便用户横向比较论文。

---

## 5.7 Obsidian 知识库导出模块

### 目标

生成属于用户自己的研究知识库，让用户方便查看每篇论文的研究方向、创新点、网络结构和 idea 启发。

### 知识库结构建议

```text
Obsidian Vault/
  LitRadar/
    Topics/
      遥感变化检测.md
      SAR 图像理解.md
    遥感变化检测/
      Daily/
        2026-05-26.md
      Papers/
        Paper-Title-A.md
        Paper-Title-B.md
      Figures/
        Paper-Title-A-Fig1.png
        Paper-Title-A-Fig2.png
      Ideas/
        idea-pool.md
```

### 每篇论文 Markdown 模板

```markdown
---
title: "论文标题"
authors: [作者1, 作者2]
year: 2025
source: "arXiv"
arxiv_id: "2501.xxxxx"
topic: "遥感变化检测"
tags: [paper, litrader, change-detection]
status: "已分析"
---

# 论文标题

## 一句话总结

## 研究方向

## 论文要解决的问题

## 输入与输出

## 整体网络框架

![[../Figures/paper-title-fig1.png]]

## 模块拆解

| 模块 | 输入 | 输出 | 作用 | 对应创新点 |
|---|---|---|---|---|

## 信息流向

## 实验与结果

## 创新点

## 局限性

## 可复现疑点

## 可以启发的新 idea

## 原文信息

- arXiv: ...
- PDF: ...
```

### Daily Radar Markdown 模板

```markdown
# 2026-05-26 每日论文雷达：遥感变化检测

## 今日推荐

### 1. Paper A

- 相关性：92/100
- 方向：SAR change detection
- 推荐理由：...
- 可能启发：...
- 链接：[[Paper A]]

### 2. Paper B

...
```

### Idea Pool

系统可以把每篇论文的 idea hints 汇总到 Topic 下的 `idea-pool.md`，方便用户找选题灵感。

---

## 6. 用户流程

## 6.1 首次配置流程

```text
打开 LitRadar
    ↓
配置 AI 中转站 Base URL、API Key、模型
    ↓
选择 Obsidian Vault
    ↓
创建研究方向 Topic
    ↓
设置关键词、arXiv 分类、每日推荐数量
    ↓
保存配置
```

## 6.2 每日论文雷达流程

```text
系统定时执行或用户手动点击“今日雷达”
    ↓
arXiv 检索候选论文
    ↓
AI 按 Topic 相关性打分
    ↓
选择前 3 篇
    ↓
生成推荐理由和 idea hint
    ↓
导出 Daily Markdown 到 Obsidian
    ↓
用户打开 Obsidian 查看今日推荐
```

## 6.3 深度阅读流程

```text
用户从今日推荐中选择一篇论文
    ↓
下载或上传 PDF
    ↓
系统解析正文和图片
    ↓
系统识别架构图候选
    ↓
用户确认关键图
    ↓
AI 使用论文结构 Skill 分析
    ↓
生成结构化阅读笔记
    ↓
导出到 Obsidian Papers 分类
```

---

## 7. API 设计草案

## 7.1 Topic 配置

```http
POST /api/topics/
GET /api/topics/
PATCH /api/topics/{topic_id}/
```

## 7.2 手动触发每日推荐

```http
POST /api/radar/run/{topic_id}/
```

返回：

```json
{
  "topic": "遥感变化检测",
  "date": "2026-05-26",
  "recommendations": [
    {
      "title": "...",
      "score": 92,
      "reason": "...",
      "idea_hint": "..."
    }
  ]
}
```

## 7.3 论文搜索

```http
GET /api/papers/search?query=remote+sensing+change+detection
```

## 7.4 保存论文

```http
POST /api/papers/
```

## 7.5 上传或关联 PDF

```http
POST /api/papers/{paper_id}/pdf/
```

## 7.6 解析 PDF

```http
POST /api/papers/{paper_id}/parse/
```

## 7.7 设置关键图

```http
PATCH /api/papers/{paper_id}/figures/{figure_id}/
```

## 7.8 结构化阅读分析

```http
POST /api/papers/{paper_id}/analyze-structure/
```

## 7.9 生成 Obsidian Markdown

```http
GET /api/papers/{paper_id}/obsidian-markdown/
GET /api/radar/{topic_id}/{date}/obsidian-markdown/
```

说明：后端生成 Markdown 内容，Tauri 负责写入本地 Vault。

---

## 8. 前端页面设计

## 8.1 页面结构

第一版建议包含 6 个页面：

1. **首页 / 今日雷达**
   - 展示每个 Topic 的今日推荐。
   - 支持手动刷新。
   - 支持一键导出 Daily Markdown。

2. **研究方向配置页**
   - 创建 Topic。
   - 编辑关键词。
   - 设置 arXiv 分类。
   - 设置每日推荐数量。
   - 设置 Obsidian 分类目录。

3. **论文搜索页**
   - 手动输入关键词检索。
   - 展示 arXiv 搜索结果。
   - 支持保存论文。

4. **论文库页**
   - 按 Topic 查看论文。
   - 查看状态：推荐、已保存、已解析、已分析、已导出。

5. **论文详情 / 深度阅读页**
   - 展示论文元数据。
   - 上传或下载 PDF。
   - 展示正文解析状态。
   - 展示图片列表。
   - 标记关键架构图。
   - 运行结构化阅读 Skill。
   - 展示分析结果。

6. **设置页**
   - AI 中转站配置。
   - 文本模型配置。
   - 视觉模型配置。
   - Obsidian Vault 路径。
   - 后端地址。

## 8.2 关键组件

- `TopicCard`
- `KeywordEditor`
- `DailyRadarPanel`
- `PaperRecommendationCard`
- `PaperLibraryTable`
- `PdfUploadPanel`
- `FigureGallery`
- `KeyFigureSelector`
- `StructureInsightView`
- `MarkdownPreview`
- `VaultPathPicker`

---

## 9. 开发阶段规划

## 阶段 1：项目骨架

目标：前后端能启动并通信。

任务：

- 创建 Tauri + Vue 3 项目。
- 创建 Django 项目。
- 配置 CORS。
- 实现 `/api/health/`。
- 前端显示后端连接状态。

验收标准：

- 桌面端能打开。
- 前端能访问 Django 后端。

## 阶段 2：研究方向与 arXiv 检索

目标：能配置 Topic，并基于 Topic 检索论文。

任务：

- 实现 ResearchTopic 数据模型。
- 实现 Topic CRUD API。
- 接入 arXiv API。
- 实现手动检索接口。
- 前端实现 Topic 配置页和论文搜索页。

验收标准：

- 用户可以创建研究方向。
- 输入关键词可以看到 arXiv 论文结果。

## 阶段 3：每日论文雷达

目标：能每天为每个 Topic 推荐固定数量论文。

任务：

- 实现候选论文去重。
- 实现 AI 相关性评分。
- 实现 DailyRecommendation 模型。
- 支持手动触发今日推荐。
- 生成 Daily Radar Markdown。

验收标准：

- 对某个 Topic 点击“运行今日雷达”。
- 系统返回 3 篇推荐论文。
- 每篇有推荐理由和 idea hint。
- 可以导出 Daily Markdown。

## 阶段 4：PDF 文本与图片解析

目标：能解析论文正文并抽取图片。

任务：

- 支持 PDF 上传或本地关联。
- 使用 PyMuPDF 提取文本。
- 使用 PyMuPDF 提取图片。
- 尝试提取 caption 和上下文。
- 前端展示 Figure Gallery。
- 用户可以标记关键图。

验收标准：

- 上传一篇论文 PDF。
- 页面显示正文解析成功。
- 页面显示抽取出的图片。
- 用户可以选择关键架构图。

## 阶段 5：论文结构 Skill 分析

目标：能生成面向网络结构理解的论文笔记。

任务：

- 实现结构化阅读 Prompt。
- 实现 AIClient。
- 支持文本降级模式。
- 如果模型支持视觉，支持关键图输入。
- 保存 PaperInsight。
- 前端展示结构化分析结果。

验收标准：

- 对一篇论文运行分析。
- 输出包含输入输出、模块拆解、信息流向、创新点、idea hint。
- 不确定内容会被标记为不确定，而不是编造。

## 阶段 6：Obsidian 知识库导出

目标：生成用户自己的结构化知识库。

任务：

- 生成每篇论文 Markdown。
- 生成 Daily Radar Markdown。
- 导出图片附件。
- Tauri 写入 Vault 指定目录。
- 前端提供 Markdown 预览。

验收标准：

- Vault 中出现 Topic 分类目录。
- Daily 推荐被写入 Daily Markdown。
- 单篇论文笔记被写入 Papers 目录。
- 论文笔记能引用本地图片附件。

## 阶段 7：演示优化

目标：形成稳定可展示的课程项目或原型产品。

任务：

- 准备固定 Topic。
- 准备固定论文 PDF。
- 准备演示 Obsidian Vault。
- 增加加载状态和错误提示。
- 美化核心页面。

验收标准：

- 可以稳定演示：配置方向 → 今日推荐 → 深度阅读 → 导出知识库。

---

## 10. 风险与取舍

## 10.1 AI 视觉能力不稳定

不同中转站和模型对图片输入支持不一致。因此不能把 MVP 完全建立在视觉模型上。

解决方式：

- 支持视觉模型时启用图像理解。
- 不支持时降级为 caption + 上下文 + 人工关键图选择。
- Markdown 中始终保留图片附件，保证用户可以人工查看。

## 10.2 arXiv 检索质量有限

arXiv 适合 AI、CV、遥感算法等方向，但不是所有领域都覆盖完整。

解决方式：

- MVP 先接 arXiv。
- 后续扩展 Semantic Scholar、CrossRef。
- AI 评分层与数据源解耦，方便替换和扩展。

## 10.3 每日自动任务在桌面端中的实现

桌面应用不一定长期运行，因此“每天自动推送”需要明确边界。

MVP 建议：

- 应用启动时检查今天是否已生成推荐。
- 如果未生成，则提示用户一键运行。
- 后续再做系统级定时任务或后台服务。

## 10.4 不建议第一版直接写 Zotero SQLite

直接修改 Zotero 数据库风险较高，容易破坏用户已有文献库。

第一版先沉淀到 LitRadar 自己的数据库和 Obsidian 知识库。Zotero 集成可以后续通过 BibTeX、CSL JSON 或 Zotero Web API 增加。

---

## 11. 推荐 MVP 范围

第一版必须完成：

- Tauri + Vue 3 桌面端。
- Django API 后端。
- AI 中转站配置。
- 用户研究方向 Topic 配置。
- arXiv 检索。
- 每日推荐 3 篇论文。
- AI 推荐理由和 idea hint。
- PDF 文本解析。
- PDF 图片抽取。
- 用户标记关键架构图。
- 论文结构 Skill 分析。
- Obsidian Daily Radar 导出。
- Obsidian 单篇论文笔记导出。

第一版暂不做：

- 直接写入 Zotero 数据库。
- 系统级后台常驻推送。
- 扫描版 PDF OCR。
- 完整 RAG 多轮问答。
- 多用户系统。
- 云端同步。
- 复杂权限系统。

---

## 12. 后续增强路线

### 12.1 更强的论文雷达

- 接入 Semantic Scholar。
- 接入 CrossRef。
- 支持引用量、代码链接、数据集信息。
- 支持按方向生成每周综述。
- 支持自动发现新的关键词。

### 12.2 更强的图文理解

- 支持视觉模型直接分析架构图。
- 支持 OCR 读取图中文字。
- 支持把网络结构图转成模块关系表。
- 支持自动生成 Mermaid 流程图。

### 12.3 更强的论文结构 Skill

- 针对不同论文类型提供不同模板：检测、分割、生成模型、多模态、综述。
- 支持多篇论文横向对比。
- 支持“这个 idea 是否已经有人做过”的反向检索。

### 12.4 Idea 工作台

- 汇总每篇论文的 idea hints。
- 按可行性、创新性、实验成本排序。
- 帮用户从知识库中生成开题方向或实验计划。

### 12.5 Zotero 集成

- 读取 Zotero 导出的 BibTeX。
- 读取 Zotero 本地条目。
- 通过 Zotero Web API 新增条目。
- 在 Obsidian 笔记中保留 Zotero citation key。

---

## 13. 推荐结论

LitRadar 的第一版应采用 **能力分层方案**：

1. 基础层保证稳定：arXiv 检索、Topic 配置、每日推荐、Obsidian 导出。
2. 增强层提升体验：PDF 文本解析、图片抽取、关键图标记。
3. 智能层体现差异化：论文结构 Skill、网络模块拆解、信息流向分析、idea hint 生成。

这样既能覆盖你的三个核心痛点，又不会把成败完全押在某个 AI 模型的视觉能力上。

最终 MVP 的一句话定义：

> LitRadar 是一个桌面端个人论文雷达，能根据用户关注方向每天发现值得阅读的论文，并把论文的研究方向、网络结构、创新点和 idea 启发沉淀成 Obsidian 知识库。
