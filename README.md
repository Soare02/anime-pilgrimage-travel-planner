# 🎌 动漫圣地巡礼旅游规划工具

An interactive SPA for anime pilgrimage ("圣地巡礼") route planning — explore, collect, and plan multi-day trips to real-world anime filming locations.

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/Vite-5-646CFF?logo=vite" alt="Vite">
  <img src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## ✨ 功能特性

- 🔍 **动漫作品搜索** — 优先从项目内置的 Anitabi 作品索引搜索名称，未命中时联网补充；也支持直接输入 Bangumi ID
- 🗺️ **取景地地图浏览** — 在 Leaflet 交互地图上查看真实取景地，支持 CartoDB / 高德地图切换
- 📸 **图像对比叠加** — 动画截图 vs 实地照片的并排对比，支持独立缩放/平移
- ⭐ **跨作品坐标库** — 收藏来自不同动漫的取景地，构建个人巡礼清单
- 🧭 **三种路线规划方案**：
  - **本地聚类** — 基于 Turf.js K-Means 空间聚类 + 最近邻排序，纯前端计算
  - **云端 AI** — 调用火山引擎 Ark API 等兼容 OpenAI 的云端大模型
  - **本地 AI** — 对接本地 LM Studio / Ollama 大模型
  - **智能体 (Agent)** — 基于 LangGraph 的多智能体协同规划（信息检索 → 空间路由 → 动漫润色 → 审查校验），集成 MiMo v2.5 视觉模型分析动漫截图
- 👁️ **视觉场景分析** — Agent 模式中自动调用 MiMo v2.5 视觉模型分析 Anitabi 动漫截图，提取光照、角度、构图等画面信息，生成精准的拍照还原指南
- 🔎 **多策略联网检索** — Agent 模式下 `get_anime_scene` 采用中文/日文/英文/站点定向多 query 召回 + 相关性打分 + DuckDuckGo 备用搜索，覆盖知乎、Bilibili、巴哈姆特、日文舞台探访博客等真实巡礼内容来源
- 🧠 **RAG 增强检索** — 人机协同的向量检索系统，核心 query 优先 + 站点定向 fallback 联网抓取巡礼攻略，人工审核后入库
- 📋 **历史记录** — 路线规划结果持久化存储，支持回看和重新加载

---

## 🖼️ 界面预览

```
┌──────────────────────────────────────────────────────┐
│  Sidebar                    │  Map (Leaflet)          │
│  ┌────────────────────┐     │                         │
│  │  搜索动漫作品        │     │     🗾 交互式地图       │
│  │  - Bangumi ID      │     │     📍 取景地标记      │
│  │  - 关键字搜索       │     │     🧭 路线连线        │
│  └────────────────────┘     │     🖼️ 图片对比        │
│  ┌────────────────────┐     │                         │
│  │  坐标库 / 历史记录  │     │                         │
│  │  - 地标收藏列表     │     │                         │
│  │  - AI 路线生成      │     │                         │
│  │  - 规划历史回看     │     │                         │
│  └────────────────────┘     │                         │
│                             ├─────────────────────────┤
│                             │  Landmark Dock (底部横栏)│
│                             │  ← 横向滚动地标卡片 →    │
└──────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 (Composition API + `<script setup>`) |
| 状态管理 | Pinia |
| UI 组件库 | Element Plus (自动按需导入) |
| 地图引擎 | Leaflet |
| 空间算法 | Turf.js (K-Means / 最近邻) |
| 构建工具 | Vite 5 |
| 后端框架 | FastAPI + Uvicorn |
| AI 框架 | LangChain + LangGraph |
| 大语言模型 | DeepSeek V4 Flash (文本推理) |
| 视觉模型 | MiMo v2.5 (动漫截图分析) |
| 向量数据库 | ChromaDB |
| Python 包管理 | uv |

---

## 📡 数据源

本项目使用了以下公开数据源和 API：

| 数据源 | 用途 | 说明 |
|--------|------|------|
| [Anitabi API](https://github.com/anitabi/anitabi.cn-document) | 动漫取景地经纬度、截图、集数信息 | 开源动漫巡礼数据库，感谢 [Anitabi 项目](https://anitabi.cn) 提供的公开 API |
| [Anitabi 作品数据](https://www.anitabi.cn/d/g.json) / [Bangumi](https://bgm.tv/) | 本地作品索引与在线补充搜索 | 名称未命中时通过 Anitabi 的 Bangumi 搜索服务查询 |
| [Tavily Search](https://tavily.com/) | 巡礼攻略联网检索 (Agent 模式) | AI 搜索引擎 |
| [wttr.in](https://wttr.in/) | 目的地实时天气 | 免费天气 API |
| MiMo v2.5 | 动漫截图视觉分析 (Agent 模式) | 小米多模态视觉模型 |

> **关于 Anitabi**：本项目依赖的开源地标数据来自 [anitabi.cn](https://anitabi.cn)，其 API 文档和数据库维护在 [anitabi/anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document)。该项目的公开 API 为本工具提供了所有取景地的经纬度、动画截图和集数对照信息。

### 名称搜索缓存

项目内置 Anitabi 作品数据快照，减少名称搜索对外部实时接口的依赖。2026-09-08 的初始快照包含 **1523 部作品**；后续更新后的数量和时间以索引文件中的 `entries`、`fetchedAt` 为准。

| 文件 | 用途 |
|------|------|
| `data/anitabi-g.json` | 保存从 `https://www.anitabi.cn/d/g.json` 下载的原始 JSON 快照 |
| `src/data/anitabi-search-index.json` | 提取名称、别名、ID、封面地址的轻量索引，记录来源、抓取时间和源数据版本，随前端打包 |
| `src/utils/bangumiSearch.js` | 本地名称匹配、在线结果适配和搜索错误处理 |
| `scripts/update-anitabi-cache.mjs` | 下载并校验源数据，同时更新原始快照和前端索引 |
| `tests/bangumi-search.test.mjs` | 名称搜索回归测试 |

搜索流程：

```text
输入作品名称
  → 匹配项目内置索引
      → 命中：直接返回候选作品，不发送在线搜索请求
      → 未命中：通过 Anitabi 在线搜索补充候选作品
  → 选中作品，取得 Bangumi ID
  → 调用 Anitabi 地标 API，显示坐标点

直接输入 Bangumi ID → 跳过名称搜索 → 调用 Anitabi 地标 API
```

本地搜索支持中文、日文、英文名称和别名，忽略大小写、空格及常见标点差异，完整名称优先。例如“你的名字。”、“君の名は。”和“YOUR NAME.”都能匹配 ID `160209`。在线搜索未完成时继续输入、收起结果或选择作品，会取消已过期的搜索请求，避免旧结果覆盖当前输入。

缓存未命中时，前端请求 `/bgm/search?keyword=...&cat=2`，由 Vite 转发到 `https://v2-anitabi.magiconch.com/api/bgm/search`，其中 `cat=2` 表示动画。在线搜索失败时分别提示超时、限流、连接错误或响应格式异常；在线接口正常返回空数组时才显示未找到作品。

**使用与更新：** 缓存已放入项目，首次使用无需下载作品索引，正常运行 `npm run dev` 即可；如果开发服务器在本次修改前已启动，请重启以加载新的代理配置。需要收录更新的作品时，手动运行：

```bash
# 更新原始快照及轻量索引
npm run cache:anitabi

# 验证本地命中、在线回退、错误提示及请求取消
npm run test:search
```

下载或数据校验失败时保留现有缓存。更新缓存后，线上版本需要重新运行 `npm run build` 并部署；生产环境需为 `/bgm/` 配置与 Vite 相同的反向代理。

**范围与限制：** 快照只覆盖 Anitabi 已收录的作品，不是 Bangumi 的全部作品库。名称命中本地缓存不依赖外部网络，但封面、坐标加载和在线补充搜索仍需联网；仅部署静态文件而不配置代理时，在线补充搜索不可用。源 JSON 和补充搜索接口为官网内部接口，未列入其稳定公开 API。

数据来源为 Anitabi，作品元数据来自 Bangumi；外部数据遵循原来源的使用条款，不属于本项目代码的 MIT 授权。

---

## 🚀 快速开始

### 环境要求

- Node.js >= 18
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) (推荐) 或 pip

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/anitabi.git
cd anitabi
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
# 前端（在网页 "AI 设置" 中输入，也可留空）
VITE_ARK_API_KEY=
VITE_ARK_MODEL=

# 后端 Agent 模式所需
DEEPSEEK_API_KEY=your_deepseek_api_key
TAVILY_API_KEY=your_tavily_api_key

# 可选：限制 / 排除搜索域名（默认放开全网，排除 github/stackoverflow 等技术站点）
# TAVILY_INCLUDE_DOMAINS=        # 留空 = 不限白名单，搜全网
# TAVILY_EXCLUDE_DOMAINS=github.com,csdn.net,stackoverflow.com,...

# MiMo 视觉模型 — Agent 模式中分析动漫截图时使用
MIMO_API_KEY=your_mimo_api_key_here
MIMO_MODEL=mimo-v2.5
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
```

<details>
<summary><b>🔧 搜索链路可选调优变量</b>（默认值已可用，仅在需要时调整）</summary>

| 变量 | 默认 | 作用 |
|------|------|------|
| `ANIME_SCENE_MAX_QUERIES` | `10` | `get_anime_scene` 单地标最大 query 数 |
| `ANIME_SCENE_ENABLE_DDG_FALLBACK` | `1` | Tavily 召回不足时是否启用 DuckDuckGo 备用搜索（`0` 关闭） |
| `RAG_TAVILY_MAX_QUERIES` | `8` | RAG 预检索单地标总 query 预算 |
| `RAG_TAVILY_CORE_QUERIES` | `4` | 核心优先 query 数（不超过总预算） |
| `RAG_TAVILY_SITE_QUERIES` | `3` | 核心召回不足时的站点定向 fallback 数 |
| `RAG_TAVILY_MIN_RESULTS` | `3` | 触发站点 fallback 的命中数阈值 |
| `RAG_TAVILY_SEARCH_DEPTH` | `basic` | RAG 预检索 Tavily 深度（`basic`/`advanced`） |
| `RAG_INGEST_MAX_WORKERS` | `3` | 批量缺失地标预检索并发数 |

> 以上变量均通过 `parse_int_env()` 安全解析：空串 / 非数字 / 未设置均回退默认值，不会导致整批检索失败。

</details>

### 3. 安装前端依赖

```bash
npm install
```

### 4. 安装后端依赖

```bash
uv sync
```

### 5. 启动服务

**终端 1 — 前端开发服务器：**

```bash
npm run dev
```

**终端 2 — 后端 Agent 服务（可选，仅在需要 Agent 模式时启动）：**

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

浏览器访问 `http://localhost:5173` 即可使用。

### 6. RAG 增强检索（可选）

如需使用 RAG 双阶段检索重排功能：

1. 安装 [LM Studio](https://lmstudio.ai/)
2. 下载并加载以下模型：
   - 向量嵌入：`text-embedding-qwen3-embedding-0.6b`
   - 重排序：`qwen3-reranker-0.6b`
3. 在 LM Studio 中开启 Local Server（默认端口 `1234`）

---

## 📁 项目结构

```
anime-travel/
├── src/                          # Vue 3 前端
│   ├── App.vue                   # 主布局
│   ├── main.js                   # 入口文件
│   ├── style.css                 # 全局样式
│   ├── stores/app.js             # Pinia 全局状态
│   ├── utils/
│   │   ├── api.js                # Anitabi / Bangumi / AI API
│   │   └── routePlanner.js       # Turf.js 空间聚类路由
│   └── components/
│       ├── SearchPanel.vue       # 动漫搜索 + AI 设置
│       ├── MapView.vue           # Leaflet 地图核心
│       ├── CoordinateLibrary.vue # 坐标库 + 历史记录
│       ├── LandmarkDock.vue      # 底部横向地标条
│       └── RagAdminPanel.vue     # RAG 数据中心管理
├── server.py                     # FastAPI 后端入口
├── agent.py                      # LangGraph 多智能体规划
├── tools.py                      # Agent 工具集（get_anime_scene 多策略搜索 + DDG 备用）
├── rag_service.py                # RAG 检索与重排服务
├── tavily_config.py              # Tavily 搜索配置 + 共享常量 + parse_int_env
├── pyproject.toml                # Python 依赖 (uv)
├── package.json                  # Node.js 依赖
├── vite.config.js                # Vite 配置
└── .env.example                  # 环境变量模板
```

---

## 🔧 三种 AI 方案说明

| 方案 | 模式 | 适用场景 | 需要启动的服务 |
|------|------|----------|---------------|
| **本地聚类** | 纯前端 Turf.js | 单个作品的快速多日分组 | 无需后端 |
| **Cloud** | 云端大模型 API | 有火山引擎 / OpenAI 兼容 API Key | Vite 开发服务器 |
| **Local** | 本地大模型 | 有 LM Studio / Ollama 本地部署 | 本地模型服务 |
| **Agent** | Python 智能体 + MiMo 视觉 | 多作品综合巡礼，联网检索 + 截图视觉分析 | FastAPI 后端 |

在网页 "AI 设置" 对话框中可自由切换，配置自动保存到浏览器。

---

## 🤝 致谢

- [Anitabi](https://anitabi.cn) / [anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document) — 提供开源动漫取景地数据库和公开 API
- [Bangumi](https://bgm.tv) — ACG 作品索引与搜索
- [Leaflet](https://leafletjs.com/) — 开源交互式地图库
- [Turf.js](https://turfjs.org/) — 浏览器端地理空间分析
- [Element Plus](https://element-plus.org/) — Vue 3 UI 组件库
- [LangChain](https://www.langchain.com/) + [LangGraph](https://langchain-ai.github.io/langgraph/) — AI Agent 框架
- [DeepSeek](https://www.deepseek.com/) — 大语言模型
- [MiMo](https://xiaomimimo.com/) — 多模态视觉模型
- [ChromaDB](https://www.trychroma.com/) — 开源向量数据库
- [LM Studio](https://lmstudio.ai/) — 本地大模型部署

---

## 📄 License

MIT
