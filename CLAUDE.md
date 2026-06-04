# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

动漫圣地巡礼旅游规划工具 — 动漫取景地浏览、收藏与多日行程规划。前端 Vue 3 SPA + 后端 Python LangChain Agent。

## Project Structure

```
├── src/                          # Vue 3 frontend
│   ├── App.vue                   # Layout: sidebar (SearchPanel + CoordinateLibrary) + map + dock
│   ├── main.js                   # Entry: createApp + Pinia + Element Plus
│   ├── style.css                 # Global styles, Leaflet popup overrides, CSS variables, day colors
│   ├── stores/app.js             # Single Pinia store — ALL app state
│   ├── utils/
│   │   ├── api.js                # Anitabi, Bangumi, AI route API calls
│   │   └── routePlanner.js       # Turf.js K-means clustering + nearest-neighbor sort
│   └── components/
│       ├── SearchPanel.vue       # Anime search (keyword/ID) + AI settings dialog
│       ├── MapView.vue           # Leaflet map, markers, route polylines, image comparison overlay
│       ├── CoordinateLibrary.vue # Landmark library + route history (tabs) + AI response render
│       ├── LandmarkDock.vue      # Bottom horizontal scrollable landmark strip
│       └── LandmarkPopup.vue     # Reusable popup content (NOT used — MapView builds HTML strings)
├── server.py                     # FastAPI — /api/agent/plan streaming endpoint
├── agent.py                      # LangChain agent: DeepSeek + Tavily tools, route planning system prompt
├── tools.py                      # LangChain tools: get_weather, get_attraction, get_anime_scene
├── pyproject.toml                # Python deps (managed with uv): fastapi, langchain, langgraph, tavily, etc.
├── package.json                  # Node deps: vue 3, pinia, element-plus, leaflet, @turf/turf, vite
├── vite.config.js                # Vite: Element Plus auto-import, proxy /ark + /api
├── .env                          # VITE_ARK_API_KEY, DEEPSEEK_API_KEY, TAVILY_API_KEY
├── 技术方案文档.md                 # Old design doc — OUTDATED
└── 技术方案文档.md.bak             # Will be updated
```

## Current Layout (App.vue)

```
App.vue
├── aside.sidebar
│   ├── SearchPanel           (search + AI settings dialog)
│   └── CoordinateLibrary     (tabs: 坐标库 / 历史记录)
└── main.main-content
    ├── MapView               (Leaflet map + tile switcher + image comparison)
    └── LandmarkDock          (bottom floating strip)
```

**NOT used:** `LandmarkList.vue` — exists but not imported anywhere.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend framework | Vue 3 (Composition API, `<script setup>`) |
| State management | Pinia (single store) |
| UI components | Element Plus (auto-imported) |
| Map | Leaflet (raw `L.map()` — NOT vue-leaflet) |
| Geospatial | Turf.js (K-means, distance) |
| Build | Vite 5 |
| Backend | FastAPI + Uvicorn |
| AI framework | LangChain (create_agent) + LangGraph (stream) |
| AI models | DeepSeek API (agent), Ark API (cloud), LM Studio/Ollama (local) |
| AI tools | Tavily Search, wttr.in weather |
| Python manager | uv |

## Three AI Route-Planning Schemes

Switchable in SearchPanel's settings dialog. Config persisted to localStorage.

| Scheme | Backend | Endpoint configured in UI |
|--------|---------|--------------------------|
| **Cloud** (default) | Ark API (Volcengine) | `/ark/bots/chat/completions` → proxied to `ark.cn-beijing.volces.com/api/v3` |
| **Local** | LM Studio / Ollama | `http://localhost:11434/v1/chat/completions` |
| **Agent** | LangChain agent via FastAPI | `/api/agent/plan` → proxied to `127.0.0.1:8000` |

## Data Flow

```
Search keyword → Bangumi API (bgm.tv/search/subject)
  or Bangumi ID → Anitabi API (anitabi.cn/bangumi/{id}/lite + /points/detail)
    → Pinia store (app.js)
      → MapView (markers, popups)
      → LandmarkDock (bottom strip)
      → CoordinateLibrary (collect landmarks)
        → Generate route:
            ├── Turf.js K-means + nearest-neighbor (client-side, for current anime's points)
            └── AI API (Ark/Ollama/Agent) → Markdown itinerary (for library landmarks)
```

## Pinia Store Structure (stores/app.js)

Single store, `useAppStore()`.

| Domain | Key refs | Details |
|--------|----------|---------|
| Current anime | `bangumi`, `points`, `searchResults` | From Anitabi API |
| Map interaction | `selectedPointId`, `compareData` | Triggers popup/comparison in MapView |
| Client route | `itinerary`, `days` | From routePlanner.js |
| Library | `coordinateLibrary`, `libraryDays`, `libraryAiResponse` | Cross-anime landmark collection |
| History | `routeHistory` | localStorage, expandable with lazy-loaded API data |
| AI config | `aiConfig` | 3 schemes, persisted to localStorage |
| UI state | `loading`, `error` | Global |

## Vite Proxy Config

```js
// vite.config.js
proxy: {
  '/ark':     'https://ark.cn-beijing.volces.com/api/v3' + rewrite path
  '/api':     'http://127.0.0.1:8000'
}
```

## Python Backend Details

- **server.py**: FastAPI app, single endpoint `POST /api/agent/plan`, returns `StreamingResponse`
- **agent.py**: Uses `langchain.agents.create_agent` (LangGraph-based) with DeepSeek model + 3 Tavily/wttr.in tools. Has detailed system prompt for route planning (Chinese).
- **tools.py**: 3 tools in TOOLS list (`get_weather`, `get_attraction`, `get_anime_scene`). Also defines `get_time` and `get_yg` but NOT exported.
- **Agent model**: `deepseek-v4-flash` via `https://api.deepseek.com`, thinking disabled.

## Key Implementation Notes

- **MapView uses raw Leaflet** (`L.map()`), NOT `@vue-leaflet/vue-leaflet` (that dep may be unused)
- **Popups are HTML strings**, not Vue components — `createPopupContent()` builds HTML, `LandmarkPopup.vue` is unused
- **Element Plus auto-import**: unplugin-vue-components + unplugin-auto-import, no manual `import ElButton` needed
- **CSS day colors**: `.day-1` through `.day-7` in style.css (`#409EFF, #67C23A, #E6A23C, #F56C6C, #909399, #b37feb, #36cfc9`)
- **Leaflet zoom control offset**: pushed right (left: 390px) to avoid sidebar overlap
- **AI response**: Markdown rendered client-side by `renderMarkdown()` (not a library — custom function in CoordinateLibrary.vue)
- **No tests** in the project

## Common Commands

```bash
# Frontend dev server
npm run dev

# Python agent backend
uv run uvicorn server:app --host 127.0.0.1 --port 8000 --reload

# Production build
npm run build
npm run preview

# Python deps (if adding)
uv add <package>
```
