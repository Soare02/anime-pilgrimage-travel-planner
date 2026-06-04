<template>
  <div class="admin-panel">
    <!-- 顶部栏 -->
    <header class="admin-header">
      <div class="admin-header-left">
        <button class="back-btn" @click="handleBack" title="返回地图">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <h1 class="admin-title">RAG 数据中心</h1>
        <span class="admin-subtitle">知识库管理与审核后台</span>
      </div>
      <div class="admin-header-right">
        <div class="status-dot" :class="{ active: true }"></div>
        <span class="status-text">系统运行中</span>
      </div>
    </header>

    <div class="admin-body">
      <!-- 左侧导航 -->
      <nav class="admin-nav">
        <button
          v-for="tab in navTabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="handleTabSwitch(tab.key)"
        >
          <el-icon :size="18"><component :is="tab.icon" /></el-icon>
          <span class="nav-label">{{ tab.label }}</span>
          <span v-if="tab.key === 'pending' && pendingList.length > 0" class="nav-badge">
            {{ pendingList.length }}
          </span>
        </button>
      </nav>

      <!-- 右侧内容区 -->
      <main class="admin-main">
        <!-- ============ Tab 1: 待审核切片 ============ -->
        <div v-if="activeTab === 'pending'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">待审核切片</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingPending" @click="fetchPending">
                <el-icon v-if="!loadingPending"><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>

          <div v-if="loadingPending" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>加载待审核队列...</span>
          </div>

          <div v-else-if="pendingList.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><CircleCheck /></el-icon>
            <h3 class="empty-title">队列为空</h3>
            <p class="empty-desc">当前没有待审核的地标切片，所有数据均已处理完毕。</p>
          </div>

          <div v-else class="pending-grid">
            <div
              v-for="item in pendingList"
              :key="item.id"
              class="pending-card"
              :class="{ selected: selectedPendingId === item.id }"
              @click="selectPending(item)"
            >
              <div class="pending-card-header">
                <span class="pending-name">{{ item.landmark_name }}</span>
                <el-tag size="small" type="warning" effect="plain">{{ item.chunks?.length || 0 }} 切片</el-tag>
              </div>
              <div class="pending-card-meta">
                <span class="pending-bangumi">{{ item.bangumi }}</span>
                <span class="pending-time">{{ item.timestamp }}</span>
              </div>
              <div class="pending-sources" v-if="item.sources?.length">
                <span class="source-label">来源:</span>
                <span v-for="(src, i) in item.sources.slice(0, 2)" :key="i" class="source-url" :title="src">
                  {{ formatUrl(src) }}
                </span>
                <span v-if="item.sources.length > 2" class="source-more">+{{ item.sources.length - 2 }}</span>
              </div>
            </div>
          </div>

          <!-- 切片编辑区 -->
          <div v-if="selectedPending" class="chunk-editor-section">
            <div class="editor-header">
              <h3 class="editor-title">
                <el-icon><Edit /></el-icon>
                编辑切片: {{ selectedPending.landmark_name }}
              </h3>
              <div class="editor-actions">
                <el-button size="small" @click="addChunk">
                  <el-icon><Plus /></el-icon>
                  新增切片
                </el-button>
              </div>
            </div>

            <div class="chunks-list scrollbar-wrapper">
              <div
                v-for="(chunk, idx) in editingChunks"
                :key="idx"
                class="chunk-card"
              >
                <div class="chunk-card-header">
                  <span class="chunk-index">切片 #{{ idx + 1 }}</span>
                  <el-button
                    text
                    size="small"
                    type="danger"
                    @click="removeChunk(idx)"
                    title="删除此切片"
                  >
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-input
                  v-model="editingChunks[idx]"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 8 }"
                  resize="vertical"
                />
              </div>
            </div>

            <div class="editor-footer">
              <el-button
                type="danger"
                plain
                @click="handleReject"
                :loading="actionLoading"
              >
                <el-icon><CircleClose /></el-icon>
                拒绝写入
              </el-button>
              <el-button
                type="primary"
                @click="handleApprove"
                :loading="actionLoading"
              >
                <el-icon><CircleCheck /></el-icon>
                同意并写入 Chroma
              </el-button>
            </div>
          </div>
        </div>

        <!-- ============ Tab 2: 已入库地标 ============ -->
        <div v-if="activeTab === 'database'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">已入库地标</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingLandmarks" @click="fetchLandmarks">
                <el-icon v-if="!loadingLandmarks"><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button size="small" type="danger" plain @click="handleClearDatabase">
                <el-icon><Delete /></el-icon>
                清空数据库
              </el-button>
            </div>
          </div>

          <div v-if="loadingLandmarks" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>加载地标数据...</span>
          </div>

          <div v-else-if="dbLandmarks.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Files /></el-icon>
            <h3 class="empty-title">数据库为空</h3>
            <p class="empty-desc">向量数据库中暂无已入库的地标数据。请先在坐标库中选中地标并生成路线，然后在"待审核切片"中批准写入。</p>
          </div>

          <div v-else>
            <div class="db-stats-bar">
              <div class="stat-item">
                <span class="stat-value">{{ dbLandmarks.length }}</span>
                <span class="stat-label">地标总数</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ totalDbChunks }}</span>
                <span class="stat-label">切片总数</span>
              </div>
            </div>

            <div class="db-landmark-list">
              <div
                v-for="lm in dbLandmarks"
                :key="lm.id"
                class="db-landmark-card"
              >
                <div class="db-lm-main" @click="toggleLandmarkExpand(lm.id)">
                  <div class="db-lm-info">
                    <span class="db-lm-name">{{ lm.name }}</span>
                    <span class="db-lm-bangumi">{{ lm.bangumi }}</span>
                  </div>
                  <div class="db-lm-right">
                    <el-tag size="small" effect="plain">{{ lm.chunks_count }} Chunks</el-tag>
                    <el-button
                      text
                      size="small"
                      type="danger"
                      @click.stop="handleDeleteLandmark(lm.id, lm.name)"
                      title="从数据库中删除"
                    >
                      <el-icon><Delete /></el-icon>
                    </el-button>
                    <el-icon class="expand-arrow" :class="{ rotated: expandedLandmarkId === lm.id }">
                      <ArrowRight />
                    </el-icon>
                  </div>
                </div>

                <!-- 展开查看切片 -->
                <div v-if="expandedLandmarkId === lm.id" class="db-lm-detail">
                  <div v-if="loadingChunks" class="loading-state compact">
                    <el-icon class="is-loading"><Loading /></el-icon>
                    <span>加载切片数据...</span>
                  </div>
                  <div v-else-if="expandedChunks.length === 0" class="detail-empty">
                    暂无切片数据
                  </div>
                  <div v-else class="detail-chunk-list">
                    <div v-for="(chunk, idx) in expandedChunks" :key="chunk.id" class="detail-chunk-item">
                      <span class="chunk-idx">切片 #{{ idx + 1 }}</span>
                      <p class="chunk-text">{{ chunk.content }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ Tab 3: 运行日志 ============ -->
        <div v-if="activeTab === 'logs'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">运行日志</h2>
            <div class="panel-actions">
              <el-button size="small" :loading="loadingLogs" @click="fetchLogs">
                <el-icon v-if="!loadingLogs"><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button size="small" type="danger" plain @click="handleClearLogs">
                <el-icon><Delete /></el-icon>
                清空日志
              </el-button>
            </div>
          </div>

          <div v-if="loadingLogs" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>读取运行日志...</span>
          </div>

          <div v-else-if="logs.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Clock /></el-icon>
            <h3 class="empty-title">暂无运行日志</h3>
            <p class="empty-desc">系统尚未进行地标录入 (ingest)、审核 (pending)、拒绝 (reject) 或召回 (recall) 操作。</p>
          </div>

          <div v-else class="logs-list">
            <div
              v-for="(log, idx) in logs"
              :key="log.timestamp + '_' + idx"
              class="log-card"
              :class="log.event_type"
            >
              <div class="log-header" @click="toggleLogExpand(idx)">
                <div class="log-header-left">
                  <el-tag
                    size="small"
                    :type="getLogTagType(log.event_type)"
                    effect="dark"
                    class="log-type-tag"
                  >
                    {{ getLogLabel(log.event_type) }}
                  </el-tag>
                  <span class="log-title">
                    <template v-if="log.event_type === 'ingest'">
                      录入 {{ log.landmarks_count }} 个地标 ({{ log.total_chunks_added }} 分块)
                    </template>
                    <template v-else-if="log.event_type === 'recall'">
                      检索: "{{ log.query }}"
                    </template>
                    <template v-else-if="log.event_type === 'pending'">
                      暂存: {{ log.landmark_name }} ({{ log.chunks_count }} 切片)
                    </template>
                    <template v-else-if="log.event_type === 'reject'">
                      拒绝: {{ log.pending_id }}
                    </template>
                    <template v-else-if="log.event_type === 'delete'">
                      删除: {{ log.landmark_id }} ({{ log.chunks_deleted }} 切片)
                    </template>
                    <template v-else>
                      {{ log.event_type }}
                    </template>
                  </span>
                </div>
                <div class="log-header-right">
                  <span class="log-time">{{ log.timestamp }}</span>
                  <el-icon class="log-arrow" :class="{ rotated: expandedLogIdx === idx }">
                    <ArrowRight />
                  </el-icon>
                </div>
              </div>

              <div v-if="expandedLogIdx === idx" class="log-detail">
                <!-- 写入详情 -->
                <template v-if="log.event_type === 'ingest'">
                  <div v-for="item in log.details" :key="item.landmark_id" class="detail-section">
                    <div class="detail-section-title">
                      地标: <strong>{{ item.landmark_name }}</strong> ({{ item.bangumi }})
                      <span class="chunks-badge">{{ item.chunks_count }} 个切片</span>
                    </div>
                    <div class="detail-chunk-list">
                      <div v-for="(chunk, cIdx) in item.chunks" :key="cIdx" class="detail-chunk-item">
                        <span class="chunk-idx">切片 #{{ cIdx + 1 }}</span>
                        <p class="chunk-text">{{ chunk }}</p>
                      </div>
                    </div>
                  </div>
                </template>

                <!-- 召回详情 -->
                <template v-else-if="log.event_type === 'recall'">
                  <div v-if="log.error" class="detail-error">
                    <span class="error-label">错误:</span>
                    <span class="error-text">{{ log.error }}</span>
                  </div>
                  <template v-else>
                    <div class="detail-section">
                      <div class="detail-section-title">
                        Chroma 粗回文本数: <strong>{{ log.recalled_count }}</strong>
                      </div>
                    </div>
                    <div class="detail-section">
                      <div class="detail-section-title">精排 Top 3 文本块:</div>
                      <div class="detail-chunk-list">
                        <div v-for="chunk in log.reranked_top_3" :key="chunk.rank" class="detail-chunk-item">
                          <div class="chunk-header-row">
                            <span class="chunk-idx">Top #{{ chunk.rank }} (评分: {{ chunk.score === -1 ? '相似度' : chunk.score.toFixed(3) }})</span>
                            <span class="chunk-source-tag">{{ chunk.landmark_name }} - {{ chunk.bangumi }}</span>
                          </div>
                          <p class="chunk-text">{{ chunk.content }}</p>
                        </div>
                      </div>
                    </div>
                    <div class="detail-section">
                      <div class="detail-section-title">注入模型 Prompt 的完整 RAG Context:</div>
                      <pre class="context-pre">{{ log.final_context || '(无数据)' }}</pre>
                    </div>
                  </template>
                </template>

                <!-- 其他事件的 raw JSON -->
                <template v-else>
                  <pre class="context-pre">{{ JSON.stringify(log, null, 2) }}</pre>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- ============ Tab 4: 召回测试 ============ -->
        <div v-if="activeTab === 'recall'" class="tab-panel">
          <div class="panel-header">
            <h2 class="panel-title">召回测试</h2>
          </div>

          <div class="recall-search-bar">
            <el-input
              v-model="recallQuery"
              placeholder="输入关键词进行向量召回 + Reranker 精排测试..."
              size="large"
              clearable
              @keyup.enter="handleRecallSearch"
            >
              <template #append>
                <el-button @click="handleRecallSearch" :loading="recallSearching">
                  <el-icon v-if="!recallSearching"><Search /></el-icon>
                  检索
                </el-button>
              </template>
            </el-input>
          </div>

          <div v-if="recallSearching" class="loading-state">
            <el-icon class="is-loading" :size="24"><Loading /></el-icon>
            <span>检索与精排中...</span>
          </div>

          <div v-else-if="recallSearched && recallResults.length === 0" class="empty-state">
            <el-icon :size="48" class="empty-icon"><Warning /></el-icon>
            <h3 class="empty-title">未召回相关文本</h3>
            <p class="empty-desc">请尝试更换查询词，或确保数据库中已录入相关作品的数据。</p>
          </div>

          <div v-else-if="!recallSearched" class="empty-state">
            <el-icon :size="48" class="empty-icon"><ChatLineRound /></el-icon>
            <h3 class="empty-title">召回与重排测试</h3>
            <p class="empty-desc">输入关键词后，系统会从向量数据库中召回候选文本块，并由 Reranker 模型重新打分排序。你可以用这个工具来验证知识库的检索精度。</p>
          </div>

          <div v-else class="recall-results">
            <div class="recall-meta">
              召回并精排前 <strong>{{ recallResults.length }}</strong> 条结果
            </div>
            <div class="recall-cards">
              <div
                v-for="item in recallResults"
                :key="item.rank"
                class="recall-card"
              >
                <div class="recall-card-header">
                  <div class="recall-left">
                    <span class="recall-rank">#{{ item.rank }}</span>
                    <span class="recall-source">{{ item.landmark_name }} ({{ item.bangumi }})</span>
                  </div>
                  <el-tag
                    size="small"
                    :type="getScoreType(item.score)"
                    effect="dark"
                  >
                    {{ item.score === -1 ? '相似度' : '分: ' + item.score.toFixed(3) }}
                  </el-tag>
                </div>
                <p class="recall-content">{{ item.content }}</p>
                <div class="recall-footer" v-if="item.source && item.source !== '未知来源'">
                  <span class="source-label">来源:</span>
                  <span class="source-val">{{ item.source }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, markRaw } from 'vue'
import {
  ArrowLeft, ArrowRight, Refresh, Delete, Edit, Plus, Search,
  Loading, CircleCheck, CircleClose, Files, Clock, Warning,
  ChatLineRound, List, DataAnalysis, Document, Monitor
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app'

const store = useAppStore()

// ---- 导航 ----
const navTabs = [
  { key: 'pending', label: '待审核切片', icon: markRaw(Document) },
  { key: 'database', label: '已入库地标', icon: markRaw(DataAnalysis) },
  { key: 'logs', label: '运行日志', icon: markRaw(Clock) },
  { key: 'recall', label: '召回测试', icon: markRaw(Monitor) }
]
const activeTab = ref('pending')

function handleBack() {
  store.showAdminPage = false
}

function handleTabSwitch(key) {
  activeTab.value = key
  if (key === 'pending') fetchPending()
  else if (key === 'database') fetchLandmarks()
  else if (key === 'logs') fetchLogs()
}

// ---- 待审核 ----
const pendingList = ref([])
const loadingPending = ref(false)
const selectedPendingId = ref(null)
const editingChunks = ref([])
const actionLoading = ref(false)

const selectedPending = computed(() => pendingList.value.find(p => p.id === selectedPendingId.value))

async function fetchPending() {
  loadingPending.value = true
  try {
    const resp = await fetch('/api/rag/pending')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    pendingList.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取待审核队列失败: ${e.message}`)
  } finally {
    loadingPending.value = false
  }
}

function selectPending(item) {
  selectedPendingId.value = item.id
  editingChunks.value = [...(item.chunks || [])]
}

function addChunk() {
  editingChunks.value.push('')
}

function removeChunk(idx) {
  editingChunks.value.splice(idx, 1)
}

async function handleApprove() {
  if (!selectedPendingId.value) return
  // 过滤掉空切片
  const validChunks = editingChunks.value.filter(c => c.trim())
  if (validChunks.length === 0) {
    ElMessage.warning('请至少保留一个有效切片')
    return
  }
  actionLoading.value = true
  try {
    const resp = await fetch('/api/rag/pending/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedPendingId.value, chunks: validChunks })
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('切片已成功写入向量数据库')
    selectedPendingId.value = null
    editingChunks.value = []
    await fetchPending()
  } catch (e) {
    ElMessage.error(`审批写入失败: ${e.message}`)
  } finally {
    actionLoading.value = false
  }
}

async function handleReject() {
  if (!selectedPendingId.value) return
  try {
    await ElMessageBox.confirm(
      `确定要拒绝并删除地标"${selectedPending.value?.landmark_name}"的所有暂存切片吗？`,
      '拒绝确认',
      { confirmButtonText: '确定拒绝', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }

  actionLoading.value = true
  try {
    const resp = await fetch('/api/rag/pending/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: selectedPendingId.value })
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('已拒绝并删除暂存记录')
    selectedPendingId.value = null
    editingChunks.value = []
    await fetchPending()
  } catch (e) {
    ElMessage.error(`拒绝操作失败: ${e.message}`)
  } finally {
    actionLoading.value = false
  }
}

// ---- 已入库地标 ----
const dbLandmarks = ref([])
const loadingLandmarks = ref(false)
const expandedLandmarkId = ref(null)
const expandedChunks = ref([])
const loadingChunks = ref(false)

const totalDbChunks = computed(() => dbLandmarks.value.reduce((sum, lm) => sum + (lm.chunks_count || 0), 0))

async function fetchLandmarks() {
  loadingLandmarks.value = true
  try {
    const resp = await fetch('/api/rag/landmarks')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    dbLandmarks.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取已入库地标失败: ${e.message}`)
  } finally {
    loadingLandmarks.value = false
  }
}

async function toggleLandmarkExpand(lmId) {
  if (expandedLandmarkId.value === lmId) {
    expandedLandmarkId.value = null
    expandedChunks.value = []
    return
  }
  expandedLandmarkId.value = lmId
  loadingChunks.value = true
  try {
    const resp = await fetch(`/api/rag/landmark/${encodeURIComponent(lmId)}/chunks`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    expandedChunks.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取切片详情失败: ${e.message}`)
    expandedChunks.value = []
  } finally {
    loadingChunks.value = false
  }
}

async function handleDeleteLandmark(lmId, lmName) {
  try {
    await ElMessageBox.confirm(
      `确定要从向量数据库中删除地标"${lmName}"的所有切片数据吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger', type: 'warning' }
    )
  } catch { return }

  try {
    const resp = await fetch(`/api/rag/landmarks/${encodeURIComponent(lmId)}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success(`已删除地标"${lmName}"的所有数据`)
    if (expandedLandmarkId.value === lmId) {
      expandedLandmarkId.value = null
      expandedChunks.value = []
    }
    await fetchLandmarks()
  } catch (e) {
    ElMessage.error(`删除失败: ${e.message}`)
  }
}

async function handleClearDatabase() {
  try {
    await ElMessageBox.confirm(
      '确定要清空 RAG 向量数据库吗？清空后已录入的所有地标切片数据均会丢失。',
      '危险操作确认',
      { confirmButtonText: '确定清空', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger', type: 'warning' }
    )
  } catch { return }

  loadingLandmarks.value = true
  try {
    const resp = await fetch('/api/rag/clear', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('向量数据库已清空')
    dbLandmarks.value = []
    expandedLandmarkId.value = null
    expandedChunks.value = []
  } catch (e) {
    ElMessage.error(`清空失败: ${e.message}`)
  } finally {
    loadingLandmarks.value = false
  }
}

// ---- 运行日志 ----
const logs = ref([])
const loadingLogs = ref(false)
const expandedLogIdx = ref(null)

async function fetchLogs() {
  loadingLogs.value = true
  expandedLogIdx.value = null
  try {
    const resp = await fetch('/api/rag/logs')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    logs.value = await resp.json()
  } catch (e) {
    ElMessage.error(`获取运行日志失败: ${e.message}`)
  } finally {
    loadingLogs.value = false
  }
}

function toggleLogExpand(idx) {
  expandedLogIdx.value = expandedLogIdx.value === idx ? null : idx
}

async function handleClearLogs() {
  try {
    await ElMessageBox.confirm('确定要清空所有运行日志吗？', '确认清空',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
  } catch { return }

  loadingLogs.value = true
  try {
    const resp = await fetch('/api/rag/logs/clear', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    ElMessage.success('运行日志已清空')
    logs.value = []
  } catch (e) {
    ElMessage.error(`清空日志失败: ${e.message}`)
  } finally {
    loadingLogs.value = false
  }
}

function getLogTagType(type) {
  const map = { ingest: 'success', recall: '', pending: 'warning', reject: 'danger', delete: 'danger' }
  return map[type] || 'info'
}

function getLogLabel(type) {
  const map = { ingest: '写入', recall: '召回', pending: '暂存', reject: '拒绝', delete: '删除' }
  return map[type] || type
}

// ---- 召回测试 ----
const recallQuery = ref('')
const recallSearching = ref(false)
const recallSearched = ref(false)
const recallResults = ref([])

async function handleRecallSearch() {
  if (!recallQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  recallSearching.value = true
  recallSearched.value = true
  try {
    const resp = await fetch(`/api/rag/query?query=${encodeURIComponent(recallQuery.value.trim())}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    recallResults.value = await resp.json()
  } catch (e) {
    ElMessage.error(`召回测试失败: ${e.message}`)
  } finally {
    recallSearching.value = false
  }
}

function getScoreType(score) {
  if (score === -1) return 'info'
  if (score >= 0.8) return 'success'
  if (score >= 0.5) return 'warning'
  return 'danger'
}

// ---- 工具函数 ----
function formatUrl(url) {
  try { return new URL(url).hostname } catch { return url?.slice(0, 30) || '' }
}

// ---- 初始化 ----
onMounted(() => {
  fetchPending()
})
</script>

<style scoped>
.admin-panel {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #f0f4f8 0%, #e8eef5 50%, #dfe7f0 100%);
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
}

/* ---- 顶部栏 ---- */
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 60px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border-bottom: 1px solid rgba(208, 215, 222, 0.5);
  flex-shrink: 0;
}

.admin-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: all 0.2s;
  color: var(--text-color);
  font-size: 16px;
}
.back-btn:hover {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
  transform: translateX(-2px);
}

.admin-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-color);
}

.admin-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(9, 105, 218, 0.08);
  padding: 2px 10px;
  border-radius: 20px;
}

.admin-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
}
.status-dot.active {
  background: #52c41a;
  box-shadow: 0 0 6px rgba(82, 196, 26, 0.5);
  animation: pulse-dot 2s infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ---- 主体 ---- */
.admin-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ---- 左侧导航 ---- */
.admin-nav {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 20px 12px;
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(20px);
  border-right: 1px solid rgba(208, 215, 222, 0.4);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: none;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  transition: all 0.2s;
  position: relative;
}
.nav-item:hover {
  background: rgba(9, 105, 218, 0.06);
  color: var(--text-color);
}
.nav-item.active {
  background: rgba(9, 105, 218, 0.1);
  color: var(--primary-color);
  font-weight: 600;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: var(--primary-color);
  border-radius: 0 3px 3px 0;
}

.nav-label { flex: 1; text-align: left; }

.nav-badge {
  background: #ff4d4f;
  color: white;
  font-size: 11px;
  font-weight: 600;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 10px;
  padding: 0 5px;
}

/* ---- 右侧内容区 ---- */
.admin-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 24px 32px;
}

.tab-panel {
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.panel-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-color);
}

.panel-actions {
  display: flex;
  gap: 8px;
}

/* ---- 通用状态 ---- */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 0;
  color: var(--text-secondary);
  font-size: 14px;
}
.loading-state.compact {
  padding: 20px 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  text-align: center;
}
.empty-icon { color: rgba(0, 0, 0, 0.12); }
.empty-title {
  margin-top: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}
.empty-desc {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 400px;
  line-height: 1.6;
}

/* ---- 待审核卡片网格 ---- */
.pending-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.pending-card {
  padding: 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.5);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s;
}
.pending-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 16px rgba(9, 105, 218, 0.1);
  transform: translateY(-2px);
}
.pending-card.selected {
  border-color: var(--primary-color);
  background: rgba(9, 105, 218, 0.04);
  box-shadow: 0 0 0 2px rgba(9, 105, 218, 0.2);
}

.pending-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.pending-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
}
.pending-card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.pending-bangumi { font-weight: 500; }

.pending-sources {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.source-label { color: var(--text-secondary); }
.source-url {
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 6px;
  border-radius: 4px;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-more {
  color: var(--primary-color);
  font-weight: 500;
}

/* ---- 切片编辑区 ---- */
.chunk-editor-section {
  margin-top: 24px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(208, 215, 222, 0.5);
  border-radius: 14px;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.editor-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}

.chunks-list {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-card {
  padding: 12px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  flex-shrink: 0;
}

.chunk-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.chunk-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
}

.editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

/* ---- 已入库地标 ---- */
.db-stats-bar {
  display: flex;
  gap: 32px;
  margin-bottom: 20px;
  padding: 16px 24px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary-color);
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.db-landmark-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.db-landmark-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.db-landmark-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.db-lm-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  cursor: pointer;
}
.db-lm-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.db-lm-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}
.db-lm-bangumi {
  font-size: 12px;
  color: var(--text-secondary);
}
.db-lm-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.expand-arrow {
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.expand-arrow.rotated { transform: rotate(90deg); }

.db-lm-detail {
  padding: 0 16px 16px;
  border-top: 1px solid var(--border-color);
}
.detail-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

/* ---- 通用切片列表 ---- */
.detail-chunk-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.detail-chunk-item {
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.02);
  border: 1px solid rgba(208, 215, 222, 0.3);
  border-radius: 8px;
}
.chunk-idx {
  font-size: 11px;
  font-weight: 600;
  color: var(--primary-color);
  margin-bottom: 4px;
  display: block;
}
.chunk-text {
  font-size: 13px;
  color: var(--text-color);
  line-height: 1.6;
  word-break: break-all;
  margin: 4px 0 0;
}
.chunk-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.chunk-source-tag {
  font-size: 11px;
  color: var(--text-secondary);
}
.chunks-badge {
  font-size: 12px;
  color: var(--primary-color);
  font-weight: 500;
  margin-left: 8px;
}

/* ---- 日志 ---- */
.logs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 10px;
  overflow: hidden;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.log-header:hover { background: rgba(0, 0, 0, 0.02); }

.log-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.log-title {
  font-size: 13px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-type-tag {
  flex-shrink: 0;
}
.log-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.log-time {
  font-size: 12px;
  color: var(--text-secondary);
}
.log-arrow {
  transition: transform 0.2s;
  color: var(--text-secondary);
}
.log-arrow.rotated { transform: rotate(90deg); }

.log-detail {
  padding: 0 16px 16px;
  border-top: 1px solid rgba(208, 215, 222, 0.3);
}

.detail-section {
  margin-top: 12px;
}
.detail-section-title {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.detail-error {
  margin-top: 12px;
  padding: 10px;
  background: rgba(245, 108, 108, 0.08);
  border-radius: 6px;
  font-size: 13px;
}
.error-label { color: #f56c6c; font-weight: 600; }
.error-text { color: var(--text-color); margin-left: 6px; }

.context-pre {
  padding: 12px;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(208, 215, 222, 0.3);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 8px;
}

/* ---- 召回测试 ---- */
.recall-search-bar {
  margin-bottom: 24px;
}

.recall-meta {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.recall-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.recall-card {
  padding: 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 12px;
  transition: box-shadow 0.2s;
}
.recall-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.recall-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.recall-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recall-rank {
  font-size: 14px;
  font-weight: 700;
  color: var(--primary-color);
}
.recall-source {
  font-size: 13px;
  color: var(--text-secondary);
}

.recall-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-color);
  word-break: break-all;
  margin: 0;
}

.recall-footer {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}
.recall-footer .source-label { margin-right: 4px; }
.recall-footer .source-val { opacity: 0.7; }

/* 滚动条 */
.admin-main::-webkit-scrollbar,
.logs-list::-webkit-scrollbar,
.chunks-list::-webkit-scrollbar {
  width: 6px;
}
.admin-main::-webkit-scrollbar-track,
.logs-list::-webkit-scrollbar-track,
.chunks-list::-webkit-scrollbar-track {
  background: transparent;
}
.admin-main::-webkit-scrollbar-thumb,
.logs-list::-webkit-scrollbar-thumb,
.chunks-list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12);
  border-radius: 3px;
}
.admin-main::-webkit-scrollbar-thumb:hover,
.logs-list::-webkit-scrollbar-thumb:hover,
.chunks-list::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}
</style>
