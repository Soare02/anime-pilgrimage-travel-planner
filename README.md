# 巡礼手帖 · 动漫圣地巡礼旅游规划工具

基于 Vue 3 与 Python LangGraph 的动漫取景地探索和行程规划工具。从作品搜索、地图浏览、跨作品收藏，到生成多日巡礼行程，在同一个工作台完成。

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/Vite-5-646CFF?logo=vite" alt="Vite">
  <img src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## ✨ 功能特性

- **发现圣地** — 名称或 Bangumi ID 搜索，内置作品索引、推荐作品与随机探索；本地未命中时联网补充。
- **取景地地图** — Leaflet 地图支持 OpenStreetMap / 高德底图切换，联动地标列表、截图弹窗和底部地标卡片。
- **照片对照** — 动画截图与用户选择的实景照片并排预览，两张图片可分别缩放。实景照片仅在浏览器本地预览。
- **我的巡礼** — 跨作品收藏地标，勾选本次行程地点并设置 1–7 天，支持批量收藏与移除。
- **三种 AI 方案** — 云端服务、本地模型与 Python Agent。云端和本地模式生成 Markdown；Agent v2 生成可校验的结构化 Plan。
- **结构化行程** — Agent 的地图连线、逐日点位、文字说明和历史记录共用一份 Plan；支持进度提示、取消、来源展示与失败草案。
- **RAG 与截图分析** — 已有知识召回、Tavily 联网补充；资料不足或服务失败时依次用百度、Bing、DuckDuckGo 搜索兜底，人工审核入库；可选 MiMo 提供截图观察和拍照建议。
- **旅途档案** — 回看历史行程，点击档案地标定位地图。
- **独立管理后台** — `/admin/` 登录后管理待审核切片、已入库地标、运行日志、召回测试与 Agent 调用追踪；所有管理读写接口统一校验会话。
- **响应式界面** — 浅色毛玻璃工作台，移动端支持侧栏内容与地图切换。

AI 设置与路线历史保存到当前浏览器的 `localStorage`；**当前收藏库只保存在页面内存，刷新后会清空**。Agent 新版历史自带地标快照，可恢复行程点位、顺序和说明；在线底图与远程图片仍需网络。

### Agent 规划结果与精度

Python Agent 默认请求 `POST /api/v2/agent/plan`，提交所选地标的原始 ID、`[纬度, 经度]` 坐标与元数据，以及正整数天数。后端用 SSE 返回运行进度、完整 Plan 或草案、错误码和终态。输入错误在调用模型前返回 HTTP 422、`INVALID_INPUT` 和字段错误。后端默认最多接受 50 个地标、30 天；当前界面的天数选择为 1–7 天。旧 `/api/agent/plan` 保留为纯文本流兼容接口，已有旧默认地址会自动迁移到 v2。

Agent 规划时显示分阶段时间线：确认地点、检索资料、天气与原作场景、路线编排、校验与修复、巡礼指南。每个阶段保留状态、耗时和根据实际执行结果生成的小结，展开可查看知识库命中、搜索线路切换、截图和天气分析、校验问题及每次返工。补排记录归在「校验与修复」，不会覆盖初稿或上一次校验结果。取消、失败和事件流中断后仍保留已收到的记录，尚未执行的阶段不会标为完成。

后端通过独立的 `step_update` SSE 事件发送这些简短记录，不传输模型原始提示词或完整调用日志，也不增加总结模型调用。成功行程的过程与输入快照一起保存到浏览器历史，可在「旅途档案 → 查看规划过程」回看；旧历史与不提供该事件的接口仍可使用。

规划流程为 `资料检索 → 天气与原作情节分析 → 分天排线 → 程序校验与内容审核 → 场景说明`，校验失败时默认最多修复 3 次。Plan 保存输入快照、逐日点位 ID 顺序、相邻点位直线距离、场景时段偏好、天气快照、每日安排理由与天气建议，以及说明、来源、未安排点和校验结果。Python 通过最近邻和有界 2-opt 整理每日顺序，同时保留上午、下午、黄昏、夜间的先后，以及同一作品在相同时段内有依据的剧情顺序；地理位置、天气与剧情偏好的取舍由每日说明展示。审核失败或修复预算耗尽时显示带具体问题的草案，草案不写入成功历史。旧版历史仍通过在线数据重新加载地标。

**距离仅指点位间直线距离。** 不含实际道路、出发地往返、步行时间、公交或铁路班次。Agent 模式可选填出发日期，天气按地标坐标分地区查询（相距较近的点位共用快照，单次最多查询 6 个地区），只将服务实际返回且日期匹配的预报用于晴雨安排。未设置日期或出行日期超出预报范围时，提供条件式建议，不把当前天气当成未来天气；天气失败会提示并继续规划。原作时段依据 RAG 与截图观察提取，片内时间戳不等于现实到访时间；资料不足时按地理位置安排。截图观察会标明未核实或推测内容，资料缺失和检索失败会显示提示。

天气快照保留带当地时刻的分时预报，以及服务返回的日出、日落时刻，黄昏场景参考当天的实际日落时间。具体时段的晴雨判断必须有对应小时数据支持；每日展示的最高降雨概率是该日各预报小时概率的最大值。展开行程中的「天气参考与预报」可查看查询时间、来源和分时数据，历史行程保留生成时的天气快照。

---

## 使用流程与界面

```
巡礼手帖   发现圣地 / 我的巡礼 / 旅途档案   AI 设置
┌──────────────────────┬─────────────────────────────┐
│ 当前导航对应的工作台    │ Leaflet 地图                │
│ · 作品搜索与取景地列表  │ · 点位、弹窗与照片对照       │
│ · 收藏选择与 AI 行程    │ · 分天着色与路线连线         │
│ · 历史行程回看         ├─────────────────────────────┤
│                      │ 底部横向地标卡片             │
└──────────────────────┴─────────────────────────────┘
移动端：在工作台与「巡礼地图」之间切换
```

1. 在「发现圣地」输入作品名或 Bangumi ID，也可点击推荐作品。
2. 在取景地列表、地图弹窗或底部卡片浏览并收藏地标；可以继续搜索其他作品。
3. 打开「AI 设置」选择规划方式，按需填写接口、密钥和模型。
4. 在「我的巡礼」勾选地点、选择天数并生成行程。Agent 模式需先启动 Python 后端。
5. 在「旅途档案」回看已保存结果。管理员通过独立地址 `/admin/` 登录后审核知识或排查调用过程，主页面不再提供管理入口。

### 档案地标与地图定位

展开「旅途档案」中的行程后，点击地标会移动地图、选中坐标并打开对应弹窗；移动端会自动切换到地图，并保持选中地标的定位。地图及底部地标卡片使用该档案的坐标数据，与当前探索作品和收藏列表分开管理。

点击档案地标、重复点击或重新展开缓存档案均不会添加收藏；收藏仍通过地图弹窗或底部卡片上的「收藏」按钮操作。新版 Agent 档案从快照恢复地标，旧版文字档案通过 Anitabi 加载详情；缺少有效坐标的地标会提示无法定位。

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 (Composition API + `<script setup>`) |
| 状态管理 | Pinia |
| UI 组件库 | Element Plus (自动按需导入) |
| 地图引擎 | Leaflet |
| 空间算法 | Python Haversine / 最近邻 / 有界 2-opt；保留 Turf.js 聚类工具 |
| 构建工具 | Vite 5 |
| 后端框架 | FastAPI + Uvicorn |
| AI 框架 | LangChain + LangGraph |
| 大语言模型 | DeepSeek（模型名称由 `.env` 的 `AGENT_MODEL` 配置） |
| 视觉模型 | MiMo v2.5 (动漫截图分析) |
| 向量数据库 | ChromaDB |
| Python 包管理 | uv |

---

## 📡 数据源

本项目使用了以下公开数据源和 API：

| 数据源 | 用途 | 说明 |
|--------|------|------|
| [Anitabi 官网地图数据](https://www.anitabi.cn/d/g.json) | 动漫取景地经纬度、截图、集数信息 | 总索引提供坐标，`gN.json` 分片提供详情，按地标 ID 合并 |
| [Anitabi 作品数据](https://www.anitabi.cn/d/g.json) / [Bangumi](https://bgm.tv/) | 本地作品索引与在线补充搜索 | 名称未命中时通过 Anitabi 的 Bangumi 搜索服务查询 |
| [Tavily Search](https://tavily.com/) | 巡礼攻略联网检索 (Agent 模式) | AI 搜索引擎 |
| 百度 / Bing / DuckDuckGo | Tavily 失败或资料不足时补充巡礼网页 | 复用旧版 HTML 搜索与正文抓取，无需额外 API Key |
| [wttr.in](https://wttr.in/) | Agent 实时天气与带日期预报 | v2 按坐标分地区查询，日期超出预报范围时仅作条件式建议 |
| MiMo v2.5 | 动漫截图视觉分析 (Agent 模式) | 小米多模态视觉模型 |

> **关于 Anitabi**：本项目依赖的地标数据来自 [anitabi.cn](https://anitabi.cn)，文档维护在 [anitabi/anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document)。地标加载现已使用官网地图数据，替代实测缺少 `geo` 的公开 `/bangumi/{id}/lite` 与 `/points/detail` 响应。截图保留来源标注与来源链接。

### 地标与坐标加载

浏览器通过同源 `/anitabi-data/` 代理读取官网地图数据，避免跨域限制：

1. `/anitabi-data/g.json` → `https://www.anitabi.cn/d/g.json`：解析作品、坐标和分片大小。
2. 根据作品在索引中的位置，只加载相应的 `/anitabi-data/gN.json` 详情分片。
3. 按地标 ID 合并坐标、名称、截图、集数和出处，供地图、收藏与历史记录共用。原来的“只显示有图地标”筛选保留。

适配逻辑集中在 `src/utils/anitabiMapData.js`。索引在当前页面会话中缓存 30 分钟，分片按数据版本缓存，并发请求共用一次下载；更换作品不重复下载相同分片。请求失败可重试；HTML 回退页、坐标越界、结构变化及索引与详情不一致会明确报错，避免显示“加载成功但零坐标”。

图片统一通过 `src/utils/imageUrl.js` 将官网 `/images/` 路径和旧 Anitabi 图片域名转换为官网当前使用的 `https://img-tc.anitabi.cn/`，卡片使用 `h160`，弹窗与对照图使用 `h360`。旧收藏、历史快照和本地搜索索引中的图片地址也会在显示时适配；其他网站的图片保留原始来源。

官网地图数据属于内部数据源，官方不保证其地址和结构稳定。开发服务器已配置代理；生产部署也必须将 `/anitabi-data/` 转发到 `https://www.anitabi.cn/d/`，例如 Nginx：

```nginx
location /anitabi-data/ {
    proxy_pass https://www.anitabi.cn/d/;
    proxy_set_header Host www.anitabi.cn;
    proxy_ssl_server_name on;
}
```

运行 `npm run test:map` 验证数据适配、缓存、异常处理和搜索收藏流程。修改代理配置后需要重启 Vite。

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
  → 加载官网地图索引及作品详情分片，显示坐标点

直接输入 Bangumi ID → 跳过名称搜索 → 加载官网地图数据
```

本地搜索支持中文、日文、英文名称和别名，忽略大小写、空格及常见标点差异，完整名称优先。例如“你的名字。”、“君の名は。”和“YOUR NAME.”都能匹配 ID `160209`。在线搜索未完成时继续输入、收起结果或选择作品，会取消已过期的搜索请求，避免旧结果覆盖当前输入。

缓存未命中时，前端请求 `/bgm/search?keyword=...&cat=2`，由 Vite 转发到 `https://v2-anitabi.magiconch.com/api/bgm/search`，其中 `cat=2` 表示动画。在线搜索失败时分别提示超时、限流、连接错误或响应格式异常；在线接口正常返回空数组时才显示未找到作品。

**使用与更新：** 缓存已放入项目，首次使用无需下载作品索引，正常运行 `npm run dev` 即可。修改代理配置后需要重启开发服务器。需要收录更新的作品时，手动运行：

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
- Python >= 3.14（仅 Python Agent / 数据中心功能需要，与 `pyproject.toml` 一致）
- [uv](https://docs.astral.sh/uv/)（后端依赖管理）

### 1. 克隆项目

```bash
git clone https://github.com/Soare02/anime-pilgrimage-travel-planner.git
cd anime-pilgrimage-travel-planner
```

### 2. 安装并启动前端

```bash
npm ci
npm run dev
```

浏览器访问 `http://localhost:5173`（端口占用时以终端输出为准）。作品搜索、地图与收藏无需启动 Python 服务；在线数据、图片和底图需要联网。云端模式的接口、API Key、模型名称在右上角「AI 设置」填写。本地模式需要先启动 LM Studio / Ollama 等兼容服务，并允许浏览器跨域访问。

### 3. 配置后端环境（可选）

使用 Agent 或数据中心时，在项目根目录创建本机配置。下面的命令只在 `.env` 不存在时复制模板：

```powershell
# Windows PowerShell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

```bash
# macOS / Linux
[ -f .env ] || cp .env.example .env
```

`.env.example` 是随代码发布的配置模板，`.env` 保存本机的真实配置，已被 Git 忽略。拉取更新后，对照模板补充缺失项，并保留已有密钥、模型名称、服务地址和搜索范围。修改后端配置后需重启 Python 服务；开发模式的 `--reload` 不保证重新读取 `.env`。真实 `.env`、管理员凭据和本地知识库不随代码上传 GitHub。

按需填写以下配置。管理员账号、密码由部署者自行设置，没有默认登录凭据：

```env
# Agent 文本模型；在 .env 中修改模型名称后重启 Python 后端
DEEPSEEK_API_KEY=your_deepseek_api_key
AGENT_MODEL=deepseek-v4-flash

# 独立管理后台；账号不能为空，密码至少 12 位
ADMIN_USERNAME=
ADMIN_PASSWORD=
ADMIN_SESSION_TTL_SECONDS=28800
# 本地 HTTP 为 0；生产 HTTPS 为 1
ADMIN_COOKIE_SECURE=0

# RAG 缺失资料联网补充所需
TAVILY_API_KEY=your_tavily_api_key

# 留空表示不限制搜索白名单；模板内预填了一组域名，可按需调整
TAVILY_INCLUDE_DOMAINS=
# TAVILY_EXCLUDE_DOMAINS=github.com,csdn.net,stackoverflow.com

# 可选：MiMo 截图分析
MIMO_API_KEY=your_mimo_api_key_here
MIMO_MODEL=mimo-v2.5
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# 可选：本地向量检索；维度需与实际模型输出一致
EMBEDDING_BASE_URL=http://localhost:1234/v1
EMBEDDING_MODEL=text-embedding-qwen3-embedding-0.6b
EMBEDDING_DIMENSION=1024
EMBEDDING_CONFIG_VERSION=1
EMBEDDING_TIMEOUT_SECONDS=5
RERANK_BASE_URL=http://localhost:1234/v1
```

模板中的 `VITE_ARK_API_KEY`、`VITE_ARK_MODEL` 当前未被前端源码读取；实际配置入口是网页「AI 设置」，其中密钥会随配置保存在当前浏览器。Tavily 未配置或调用失败时，默认尝试直接搜索兜底；MiMo 未配置时跳过截图分析，并保留相关提示。

### 4. 安装并启动 Python 后端

在第二个终端的项目根目录运行：

```bash
uv sync
uv run uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

前后端启动后可访问：

| 页面 | 默认地址 | 说明 |
|------|----------|------|
| 巡礼工作台 | `http://localhost:5173/` | 搜索、收藏与行程规划 |
| 独立管理后台 | `http://localhost:5173/admin/` | 使用 `.env` 中的管理员账号、密码登录 |
| 后端 API 文档 | `http://127.0.0.1:8000/docs` | 查看请求契约，管理接口仍需鉴权 |

回到工作台「AI 设置」选择「智能体」，默认接口为 `/api/v2/agent/plan`。前端通过同源 `/api/` 代理连接后端；管理页面也使用这一代理。管理员未配置时管理接口返回 503；配置有效但未登录时返回 401。

Agent 文本模型与 MiMo 视觉模型一样通过 `.env` 配置：修改 `AGENT_MODEL` 后重启 Python 后端即可生效，无需修改代码。未配置或留空时使用 `deepseek-v4-flash`。新旧 Agent 接口共用该模型配置，调用追踪会显示实际使用的模型名称。

### 5. 启用 RAG 向量检索与重排（可选）

1. 在 [LM Studio](https://lmstudio.ai/) 加载 embedding 模型 `text-embedding-qwen3-embedding-0.6b` 和重排模型 `qwen3-reranker-0.6b`。
2. 启动 Local Server（默认端口 `1234`），按实际服务地址配置 `EMBEDDING_BASE_URL` / `RERANK_BASE_URL`。
3. 确认 embedding 模型输出维度与 `EMBEDDING_DIMENSION` 一致。首次启动后端时会自动初始化 `chroma_db/`。

重排器通过 `/v1/responses` 与 token 概率评分，并非通用 `/rerank` 接口。重排失败会保留召回顺序；向量查询失败时，规划流程仍会保留按地标 ID 命中的已有资料并给出提示。

### 调用预算与搜索调优

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `AGENT_MAX_LANDMARKS` / `AGENT_MAX_DAYS` | `50` / `30` | 后端请求规模上限 |
| `AGENT_MAX_REVISIONS` | `3` | 校验失败后的最大修复次数 |
| `AGENT_MODEL_TIMEOUT_SECONDS` | `45` | 单次模型调用时限 |
| `AGENT_TOOL_TIMEOUT_SECONDS` | `35` | 单次资料或截图工具调用时限 |
| `AGENT_RUN_TIMEOUT_SECONDS` | `240` | 整次规划时限，单位秒 |
| `AGENT_TRACE_DEBUG` | `0` | `1` 开启额外追踪诊断 |

修改后端环境变量后需要重启 Python 服务。

<details>
<summary><b>搜索链路可选调优变量</b></summary>

| 变量 | 默认 | 作用 |
|------|------|------|
| `ANIME_SCENE_BACKEND` | `direct` | 旧版场景工具的搜索方式：`direct` / `tavily` / `auto` |
| `DIRECT_SEARCH_ENGINE` | `baidu` | 旧版直接搜索的引擎：`baidu` / `ddg` / `bing` / `both`（百度与 Bing） |
| `ANIME_SCENE_MAX_QUERIES` | `10` | 旧版 `get_anime_scene` 单地标最大 query 数 |
| `ANIME_SCENE_ENABLE_DDG_FALLBACK` | `1` | 旧版 Tavily 召回不足时是否启用 DuckDuckGo 备用搜索（`0` 关闭） |
| `RAG_TAVILY_MAX_QUERIES` | `8` | RAG 预检索单地标总 query 预算 |
| `RAG_TAVILY_CORE_QUERIES` | `4` | 核心优先 query 数（不超过总预算） |
| `RAG_TAVILY_SITE_QUERIES` | `3` | 核心召回不足时的站点定向 fallback 数 |
| `RAG_TAVILY_MIN_RESULTS` | `3` | 触发站点 fallback 的命中数阈值 |
| `RAG_TAVILY_SEARCH_DEPTH` | `basic` | RAG 预检索 Tavily 深度（`basic`/`advanced`） |
| `RAG_ENABLE_DIRECT_FALLBACK` | `1` | 新版 Tavily 不可用或有效来源不足时启用直接搜索，`0` 关闭 |
| `RAG_DIRECT_SEARCH_ENGINES` | `baidu,bing,ddg` | 新版备用引擎及顺序，补够有效来源后停止 |
| `RAG_DIRECT_MAX_QUERIES` | `2` | 每个备用引擎最多查询数，有日文原名时优先保留日文查询，上限 4 |
| `RAG_DIRECT_MAX_PAGES` | `2` | 每个备用引擎最多抓取正文的页面数，上限 5 |
| `RAG_WEB_TIMEOUT_SECONDS` | `30` | 批量联网检索总预算，受 Agent 工具与整次规划时限进一步约束 |
| `RAG_TAVILY_PHASE_TIMEOUT_SECONDS` | `12` | Tavily 核心与站点查询共用的阶段预算，为备用引擎预留时间 |
| `RAG_INGEST_MAX_WORKERS` | `3` | 批量缺失地标预检索并发数 |

当前 v2 的联网补充通过 `rag_service.py` 先使用 Tavily；未配置 Key、调用失败或有效来源少于 `RAG_TAVILY_MIN_RESULTS` 时，按 `RAG_DIRECT_SEARCH_ENGINES` 顺序复用旧版直接搜索与正文抓取。结果足够时跳过后续引擎；仍不足则合并已取得的资料。所有线路共用 URL 去重、相关性过滤、来源元数据，以及 `TAVILY_INCLUDE_DOMAINS` / `TAVILY_EXCLUDE_DOMAINS` 限制。备用引擎在抓取正文前也检查域名限制。取消或预算耗尽后不再启动后续请求，迟到结果不会写入审核队列。Agent 追踪记录触发原因、实际线路和新增来源数量。

`ANIME_SCENE_*` / `DIRECT_SEARCH_ENGINE` 仍只控制旧版 `get_anime_scene` 工具，新版使用独立的 `RAG_*` 配置。无需修改现有 `.env` 即可启用默认兜底链；直接搜索受网络和搜索引擎页面变化影响，失败会记录提示并尝试下一条线路。整型搜索预算通过 `parse_int_env()` 解析，无效值回退默认值。

</details>

---

## RAG 数据中心与运行追踪

管理后台使用独立 HTML 和入口脚本：开发环境访问 `http://localhost:5173/admin/`，生产环境访问站点的 `/admin/`。前台页面不加载管理组件；后台先向服务端验证会话，通过后才加载管理面板、请求管理数据。

在后端 `.env` 中配置管理员，并重启 Python 服务：

```env
ADMIN_USERNAME=your_admin_name
ADMIN_PASSWORD=replace_with_a_long_random_password
ADMIN_SESSION_TTL_SECONDS=28800
# 本地 HTTP 为 0；生产 HTTPS 必须改为 1
ADMIN_COOKIE_SECURE=0
```

账号不能为空，密码至少 12 位；没有默认账号密码，未配置或密码过短时，所有管理读写请求返回 HTTP 503。凭据仅在后端读取，不要使用 `VITE_` 前缀。错误凭据返回 401，同一 IP 在 5 分钟内连续失败 5 次后返回 429。

登录后使用随机的 HttpOnly、SameSite=Strict Cookie，会话默认 8 小时，可配置为 300–86400 秒；密码在后端内存中用 scrypt 派生后比较。会话由服务端保存，退出立即撤销，伪造、过期或已退出的 Cookie 均返回 401。管理写操作还必须携带与当前会话绑定的 `X-CSRF-Token`，缺失或错误返回 403；管理响应禁止缓存。浏览器仅在内存保存 CSRF token，不在 localStorage 保存管理员凭据或会话令牌。

当前会话和登录限流保存在进程内，重启后需要重新登录。后端应使用单个 Uvicorn worker；若要部署多进程或多个实例，先接入共享会话和限流存储。生产部署需启用 HTTPS、设置 `ADMIN_COOKIE_SECURE=1`，并将 `/api/` 代理到 Python 后端；前后端保持同源。静态服务器需将 `/admin/` 指向构建产物 `dist/admin/index.html`，例如 Nginx：

```nginx
location = /admin { return 301 /admin/; }
location /admin/ { try_files $uri $uri/ /admin/index.html; }
location /api/ { proxy_pass http://127.0.0.1:8000; }
```

所有 `/api/rag/*`、Agent 追踪列表、追踪详情与清空追踪接口均要求管理员身份，包括旧地址，直接调用接口也不能绕过登录。普通路线规划接口继续公开使用，规划流程中的知识检索、待审核资料积累和运行记录仍由后端执行。

当前 Agent v2 优先读取已有地标知识，结合按 ID 召回、向量搜索和本地重排；缺失资料通过 Tavily 优先、直接搜索兜底的链路补充。新抓取的资料先写入待审核队列，当次规划可以临时引用，并标记为 `unreviewed`。在「数据中心 → 待审核切片」查看来源、编辑切片并批准后，才写入向量库；来源保留 URL、标题、检索时间、关联点位和审核状态。

数据中心提供五个面板：待审核切片、已入库地标、运行日志、召回测试、Agent 追踪。追踪按运行展示节点、模型和工具的输入输出，便于排查检索不足、调用失败或行程草案。

**管理员登录后，查看待审核资料、已入库地标、运行日志和 Agent 历史追踪，只需前端与 Python 后端正常运行，无需启动 LM Studio / Ollama 等本地模型服务。** 向量检索、召回测试和切片写入等操作会调用配置的 embedding 服务；重排不可用时会保留召回顺序。

管理面板通过身份验证后按需加载，期间显示加载状态。资源加载失败或超过 20 秒时，会显示失败提示及重试按钮；退出或身份失效后卸载管理面板并清除其页面数据。

| 本地文件 | 内容 |
|----------|------|
| `chroma_db/` | Chroma 持久化向量集合 |
| `chroma_db/rag_pending.json` | 待审核资料 |
| `chroma_db/rag_history.json` | RAG 操作日志 |
| `chroma_db/agent_traces.json` | 最近最多 50 次 Agent 运行追踪 |

向量集合绑定 embedding 模型、服务地址、维度和配置版本。旧集合配置缺失或与当前配置不匹配时，暂停向量查询与写入，仍允许按地标 ID 读取。更换模型或维度需核实后建立独立版本索引；系统不会自动迁移或清空旧集合。上述本地数据目录已被 Git 忽略。

### 数据中心页面加载失败

若浏览器提示 `504 (Outdated Optimize Dep)`，说明 Vite 的前端依赖缓存已经失效。先停止本项目重复的开发服务，再运行 `npm run dev`。若仍失败，停止前端后将 `node_modules/.vite/` 移到回收站，再启动前端重建缓存。

查看历史记录时遇到此类前端资源错误，无需启动本地模型。前端回归测试中的 Vite 实例已使用 `verification_artifacts/` 下的独立缓存目录，避免覆盖正在运行的开发服务缓存。

## 后端接口

完整请求格式可在运行中的 FastAPI `/docs` 查看。

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/api/v2/agent/plan` | 结构化规划 SSE，当前默认入口 |
| `POST` | `/api/agent/plan` | 旧版 Agent 纯文本流兼容入口 |
| `POST` | `/api/admin/login` | 管理员登录，需 `X-Admin-Request: 1` |
| `GET` | `/api/admin/session` | 验证当前会话并返回 CSRF token |
| `POST` | `/api/admin/logout` | 撤销会话，需 CSRF token |
| `GET` | `/api/rag/landmarks` | 已入库地标列表 |
| `GET` | `/api/rag/landmark/{landmark_id}/chunks` | 地标知识切片 |
| `GET` | `/api/rag/query?query=...` | 召回与重排调试 |
| `GET` | `/api/rag/pending` | 待审核队列 |
| `POST` | `/api/rag/pending/approve`、`/api/rag/pending/reject` | 审核通过或拒绝 |
| `DELETE` | `/api/rag/landmarks/{landmark_id}` | 移除地标知识 |
| `POST` | `/api/rag/clear` | 清空并重建向量集合 |
| `GET` / `POST` | `/api/rag/logs` / `/api/rag/logs/clear` | 查看或清空 RAG 日志 |
| `GET` | `/api/agent/traces`、`/api/agent/trace/{run_id}` | 运行摘要与追踪详情 |
| `POST` | `/api/agent/traces/clear` | 清空追踪记录 |

上述 RAG 与追踪接口均需管理员 Cookie，写操作还需 `X-CSRF-Token`。可运行 `uv run python -m unittest discover -s tests -p test_admin_auth.py -v` 和 `npm run test:admin` 验证未授权拦截、授权读写、CSRF、会话过期、退出撤销与前端请求处理。

v2 事件包含 `event_id`、`run_id`、`type`、`payload`。正常事件序列为 `run_started → progress / step_update… → plan_ready / plan_draft / error → run_finished`；终态为 `success`、`failed` 或 `cancelled`。`step_update` 用于前台展示简短的规划过程，完整模型输入输出仅能在登录后的后台追踪中查看。只有通过校验的完整 Plan 才作为成功结果保存。

---

## 📁 项目结构

```
anime-travel/
├── src/                          # Vue 3 前端
│   ├── App.vue                   # 顶部导航与响应式工作台
│   ├── main.js                   # 入口文件
│   ├── admin/                    # 独立后台入口、登录页面与鉴权请求
│   ├── style.css                 # 全局样式
│   ├── stores/app.js             # Pinia 全局状态
│   ├── utils/
│   │   ├── api.js                # 地图 / 名称搜索 / AI 请求及 SSE 解码
│   │   ├── anitabiMapData.js     # 官网索引、分片、校验与缓存
│   │   ├── bangumiSearch.js      # 本地名称搜索与在线补充
│   │   ├── imageUrl.js           # 图片地址与分辨率适配
│   │   ├── planningProgress.js   # 规划过程事件归并、终态与历史恢复
│   │   ├── recommendations.js    # 推荐作品与搜索快捷入口
│   │   └── routePlanner.js       # 保留的 Turf.js 聚类工具
│   ├── data/anitabi-search-index.json # 随前端打包的作品索引
│   └── components/
│       ├── SearchPanel.vue       # 作品搜索、推荐与取景地列表
│       ├── AiSettingsDialog.vue  # 全局 AI 设置
│       ├── MapView.vue           # Leaflet 地图核心
│       ├── CoordinateLibrary.vue # 我的巡礼与旅途档案
│       ├── PlanResult.vue        # Agent Plan 逐日结果、草案和来源
│       ├── PlanningTimeline.vue  # 规划阶段、耗时与返工过程
│       ├── LandmarkDock.vue      # 底部横向地标条
│       ├── RagAdminPanel.vue     # RAG 数据中心与 Agent 追踪
│       ├── AppIcon.vue           # 公共图标
│       └── JourneyArtwork.vue    # 界面插画
├── server.py                     # FastAPI 后端入口
├── admin_auth.py                 # 管理员认证、会话、CSRF 与登录限流
├── admin/index.html              # 独立管理页面 /admin/
├── agent.py                      # 旧版 Agent 兼容流程与共用模型
├── agent_v2.py                   # 结构化 LangGraph 规划与有限修复
├── agent_trace.py                # 运行追踪与本地持久化
├── planning_progress.py          # 用户可见的阶段执行摘要
├── weather_service.py            # 按坐标查询带日期和时段的天气快照
├── plan_schema.py                # 请求与 Plan 数据契约
├── plan_geometry.py              # 直线距离和确定性排序
├── plan_validation.py            # ID、天数、路段及状态校验
├── tools.py                      # Agent 工具集（get_anime_scene 多策略搜索 + DDG 备用）
├── rag_service.py                # RAG 检索与重排服务
├── search_runtime.py             # 可取消的搜索并发收集与时间预算
├── tavily_config.py              # Tavily 搜索配置 + 共享常量 + parse_int_env
├── data/anitabi-g.json           # 官网原始索引快照
├── scripts/update-anitabi-cache.mjs # 搜索缓存更新脚本
├── tests/                        # 前端 Node 测试与后端 unittest
├── pyproject.toml                # Python 依赖 (uv)
├── package.json                  # Node.js 依赖
├── vite.config.js                # Vite 配置
└── .env.example                  # 环境变量模板
```

---

## 🔧 三种 AI 方案说明

| 方案 | 默认接口 / 模型 | 结果 | 额外服务 |
|------|-----------------|------|----------|
| **Cloud（默认）** | `/ark/bots/chat/completions`；Key 与模型需填写 | Markdown 文字行程 | 云端兼容 Chat Completions 服务 |
| **Local** | `http://localhost:11434/v1/chat/completions` / `deepseek-r1:7b` | Markdown 文字行程 | LM Studio / Ollama 等本地模型服务 |
| **Agent** | `/api/v2/agent/plan` / `deepseek-v4-flash` | 结构化 Plan、地图路线、逐日说明及来源 | FastAPI；Tavily、MiMo 与本地 RAG 按需配置 |

在右上角「AI 设置」切换方案。Cloud 和 Local 的地址、Key、模型可编辑；当前 UI 固定使用配置中的 Agent 地址。LM Studio 用户需将 Local 默认地址改为自己的端口和模型名。

Turf.js K-Means + 最近邻算法仍保留在 `src/utils/routePlanner.js` 和 store 中，但当前界面没有调用入口。它不属于上述三种可选 AI 方案。

## 验证与构建

```bash
# 名称搜索、地图适配与缓存、Agent SSE、规划过程与历史快照回归
npm run test:search
npm run test:map
npm run test:agent

# 管理后台请求、登录失效处理与 CSRF
npm run test:admin

# 不加载 Agent / RAG 的后端契约检查
uv run python -B -m unittest discover -s tests -p test_plan_contract.py

# 后端完整回归（模型和联网调用使用模拟）
uv run python -B -m unittest discover -s tests -p 'test_*.py'

# 生成 dist/，然后进行本地静态预览
npm run build
npm run preview
```

完整后端回归导入 RAG 模块时会初始化或打开本地 `chroma_db/`，模型和联网请求使用模拟。后台鉴权回归将知识库、审核队列、日志和追踪操作替换为 mock，覆盖全部 13 个管理接口的匿名拦截、授权读写、CSRF、过期、退出撤销和登录限流。前端回归覆盖 SSE 分块、中断、终态、草案状态、规划过程、天气展示、快照与旧版档案恢复、重复定位及收藏隔离；不需要调用真实模型。前端尚未配置统一 `npm test` 命令。

构建同时生成 `dist/index.html`（前台）和 `dist/admin/index.html`（管理后台）；部署时保留这两个页面及其引用的资源。真实 `.env` 和 `chroma_db/` 保存在后端主机，不放入静态发布目录。

### 生产部署

`npm run preview` 默认继承 `vite.config.js` 中的开发代理，可用于本地构建检查；单独部署 `dist/` 静态文件时，需按所用功能配置反向代理：

| 前缀 | 上游 | 路径处理 |
|------|------|----------|
| `/anitabi-data/` | `https://www.anitabi.cn/d/` | 将前缀替换为 `/d/` |
| `/bgm/` | `https://v2-anitabi.magiconch.com/api/bgm/` | 将前缀替换为 `/api/bgm/` |
| `/ark/` | `https://ark.cn-beijing.volces.com/api/v3/` | 将前缀替换为 `/api/v3/` |
| `/api/` | `http://127.0.0.1:8000/api/` | 保留原请求路径 |

管理接口内置管理员会话鉴权，写操作额外校验 CSRF；生产环境使用 HTTPS，设置 `ADMIN_COOKIE_SECURE=1`，前后端保持同源，后端使用单个 Uvicorn worker。管理页面路由配置见上方「RAG 数据中心与运行追踪」。CORS 默认仅允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`，生产浏览器通过站点自己的 `/api/` 代理访问。

Agent 的 SSE 转发需要关闭响应缓冲，并设置足够的读取超时。例如 `/api/` 的 Nginx 配置：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

普通路线规划接口仍公开提供服务；需要限制调用者或请求频率时，在部署网关配置相应认证和限流。

---

## 🤝 致谢

- [Anitabi](https://anitabi.cn) / [anitabi.cn-document](https://github.com/anitabi/anitabi.cn-document) — 动漫取景地数据与使用文档
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
