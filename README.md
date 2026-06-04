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

- 🔍 **动漫作品搜索** — 通过关键字或 Bangumi ID 查找动漫作品
- 🗺️ **取景地地图浏览** — 在 Leaflet 交互地图上查看真实取景地，支持 CartoDB / 高德地图切换
- 📸 **图像对比叠加** — 动画截图 vs 实地照片的并排对比，支持独立缩放/平移
- ⭐ **跨作品坐标库** — 收藏来自不同动漫的取景地，构建个人巡礼清单
- 🧭 **三种路线规划方案**：
  - **本地聚类** — 基于 Turf.js K-Means 空间聚类 + 最近邻排序，纯前端计算
  - **云端 AI** — 调用火山引擎 Ark API 等兼容 OpenAI 的云端大模型
  - **本地 AI** — 对接本地 LM Studio / Ollama 大模型
  - **智能体 (Agent)** — 基于 LangGraph 的多智能体协同规划（信息检索 → 空间路由 → 动漫润色 → 审查校验）
- 🧠 **RAG 增强检索** — 人机协同的向量检索系统，联网抓取巡礼攻略，人工审核后入库
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
| 向量数据库 | ChromaDB |
| Python 包管理 | uv |

---

## 📡 数据源

本项目使用了以下公开数据源和 API：

| 数据源 | 用途 | 说明 |
|--------|------|------|
| [Anitabi API](https://github.com/anitabi/anitabi.cn-document) | 动漫取景地经纬度、截图、集数信息 | 开源动漫巡礼数据库，感谢 [Anitabi 项目](https://anitabi.cn) 提供的公开 API |
| [Bangumi API](https://bgm.tv/) | 动漫作品元数据搜索 | 中文 ACG 社区索引 |
| [Tavily Search](https://tavily.com/) | 巡礼攻略联网检索 (Agent 模式) | AI 搜索引擎 |
| [wttr.in](https://wttr.in/) | 目的地实时天气 | 免费天气 API |

> **关于 Anitabi**：本项目依赖的开源地标数据来自 [anitabi.cn](https://anitabi.cn)，其 API 文档和数据库维护在 [anitabi/anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document)。该项目的公开 API 为本工具提供了所有取景地的经纬度、动画截图和集数对照信息。

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
```

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
│       ├── ItineraryPanel.vue    # 行程卡片列表
│       └── RagAdminPanel.vue     # RAG 数据中心管理
├── server.py                     # FastAPI 后端入口
├── agent.py                      # LangGraph 多智能体规划
├── tools.py                      # Agent 工具集
├── rag_service.py                # RAG 检索与重排服务
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
| **Agent** | Python 智能体 | 多作品综合巡礼，需要联网检索 | FastAPI 后端 |

在网页 "AI 设置" 对话框中可自由切换，配置自动保存到浏览器。

---

## 🤝 致谢

- [Anitabi](https://anitabi.cn) / [anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document) — 提供开源动漫取景地数据库和公开 API
- [Bangumi](https://bgm.tv) — ACG 作品索引与搜索
- [Leaflet](https://leafletjs.com/) — 开源交互式地图库
- [Turf.js](https://turfjs.org/) — 浏览器端地理空间分析
- [Element Plus](https://element-plus.org/) — Vue 3 UI 组件库
- [LangChain](https://www.langchain.com/) + [LangGraph](https://langchain-ai.github.io/langgraph/) — AI Agent 框架
- [ChromaDB](https://www.trychroma.com/) — 开源向量数据库
- [LM Studio](https://lmstudio.ai/) — 本地大模型部署

---

## 📄 License

MIT
