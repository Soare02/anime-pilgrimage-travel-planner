<template>
  <div class="rag-console">
    <!-- Sub tabs -->
    <div class="console-sub-header">
      <div class="sub-tabs">
        <button
          class="sub-tab"
          :class="{ active: activeSubTab === 'overview' }"
          @click="activeSubTab = 'overview'"
        >
          数据源列表
        </button>
        <button
          class="sub-tab"
          :class="{ active: activeSubTab === 'recall' }"
          @click="activeSubTab = 'recall'"
        >
          召回测试
        </button>
        <button
          class="sub-tab"
          :class="{ active: activeSubTab === 'logs' }"
          @click="activeSubTab = 'logs'; fetchLogs()"
        >
          运行日志
        </button>
      </div>
      
      <!-- Sub Actions -->
      <div class="sub-actions">
        <template v-if="activeSubTab === 'overview'">
          <el-button
            circle
            size="small"
            :loading="loadingLandmarks"
            @click="fetchLandmarks"
            title="刷新数据"
          >
            <el-icon v-if="!loadingLandmarks"><Refresh /></el-icon>
          </el-button>
          <el-button
            circle
            size="small"
            type="danger"
            plain
            @click="handleClearDatabase"
            title="清空数据库"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
        <template v-else-if="activeSubTab === 'logs'">
          <el-button
            circle
            size="small"
            :loading="loadingLogs"
            @click="fetchLogs"
            title="刷新日志"
          >
            <el-icon v-if="!loadingLogs"><Refresh /></el-icon>
          </el-button>
          <el-button
            circle
            size="small"
            type="danger"
            plain
            @click="handleClearLogs"
            title="清空运行日志"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </div>
    </div>

    <!-- Data source list -->
    <div v-show="activeSubTab === 'overview'" class="tab-content scrollbar-wrapper">
      <div v-if="loadingLandmarks" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载数据源...</span>
      </div>

      <div v-else-if="landmarks.length === 0" class="empty-state">
        <el-icon :size="24" class="empty-icon"><Files /></el-icon>
        <span class="empty-text">数据库暂未录入地标数据</span>
        <span class="empty-hint">在“坐标库”中选中地标生成路线，系统将自动进行联网检索并录入 RAG 数据库。</span>
      </div>

      <div v-else class="landmarks-list">
        <div class="db-stats">
          <span>共录入 <strong>{{ landmarks.length }}</strong> 个地标</span>
          <span>总分块: <strong>{{ totalChunks }}</strong></span>
        </div>
        
        <div
          v-for="lm in landmarks"
          :key="lm.id"
          class="landmark-card"
        >
          <div class="lm-main">
            <div class="lm-title-row">
              <span class="lm-name">{{ lm.name }}</span>
              <el-tag size="small" type="info" effect="plain">{{ lm.chunks_count }} Chunks</el-tag>
            </div>
            <div class="lm-sub" v-if="lm.bangumi">
              <span class="lm-bangumi-label">对应作品:</span>
              <span class="lm-bangumi-value">{{ lm.bangumi }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Recall test -->
    <div v-show="activeSubTab === 'recall'" class="tab-content scrollbar-wrapper">
      <div class="search-box">
        <el-input
          v-model="queryText"
          placeholder="输入关键词进行召回测试..."
          size="small"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button size="small" @click="handleSearch" :loading="searching">
              <el-icon v-if="!searching"><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>

      <div v-if="searching" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>检索与精排中...</span>
      </div>

      <div v-else-if="searched && recallResults.length === 0" class="empty-state">
        <el-icon :size="24" class="empty-icon"><HelpFilled /></el-icon>
        <span class="empty-text">未召回相关文本</span>
        <span class="empty-hint">请尝试更换查询词，或确保数据库中已录入该作品的数据。</span>
      </div>

      <div v-else-if="!searched" class="empty-state recall-prompt">
        <el-icon :size="24" class="empty-icon"><ChatLineRound /></el-icon>
        <span class="empty-text">召回与重排测试</span>
        <span class="empty-hint">这里可以测试 RAG 的检索精度。系统会返回向量库召回的前 6 个文本块，并由重排模型 (Reranker) 重新打分。</span>
      </div>

      <div v-else class="recall-list">
        <div class="recall-meta">
          <span>召回并精排前 <strong>{{ recallResults.length }}</strong> 条结果</span>
        </div>
        
        <div
          v-for="item in recallResults"
          :key="item.rank"
          class="recall-card"
        >
          <div class="recall-header">
            <div class="recall-header-left">
              <span class="recall-rank">#{{ item.rank }}</span>
              <span class="recall-source-info">{{ item.landmark_name }} ({{ item.bangumi }})</span>
            </div>
            <el-tag
              size="small"
              :type="getScoreTagType(item.score)"
              effect="dark"
              class="recall-score-tag"
            >
              {{ item.score === -1 ? '相似度' : '分: ' + formatScore(item.score) }}
            </el-tag>
          </div>
          
          <div class="recall-body">
            <p class="recall-text">{{ item.content }}</p>
          </div>

          <div class="recall-footer" v-if="item.source">
            <span class="source-label">来源:</span>
            <span class="source-value" :title="item.source">{{ formatSource(item.source) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Logs / History -->
    <div v-show="activeSubTab === 'logs'" class="tab-content scrollbar-wrapper">
      <div v-if="loadingLogs" class="loading-state">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>读取运行日志...</span>
      </div>

      <div v-else-if="logs.length === 0" class="empty-state">
        <el-icon :size="24" class="empty-icon"><Clock /></el-icon>
        <span class="empty-text">暂无运行日志</span>
        <span class="empty-hint">系统尚未进行地标录入 (ingest) 或智能体路线规划 (recall) 操作。</span>
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
                :type="log.event_type === 'ingest' ? 'warning' : 'success'"
                effect="plain"
                class="log-type-tag"
              >
                {{ log.event_type === 'ingest' ? '写入' : '召回' }}
              </el-tag>
              <span class="log-title" v-if="log.event_type === 'ingest'">
                录入 {{ log.landmarks_count }} 个地标 ({{ log.total_chunks_added }} 分块)
              </span>
              <span class="log-title" v-else-if="log.event_type === 'recall'">
                检索: "{{ log.query }}"
              </span>
            </div>
            <div class="log-header-right">
              <span class="log-time">{{ formatLogTime(log.timestamp) }}</span>
              <el-icon class="log-arrow" :class="{ rotated: expandedLogIndex === idx }">
                <ArrowRight />
              </el-icon>
            </div>
          </div>

          <!-- Log Expandable Detail -->
          <div v-if="expandedLogIndex === idx" class="log-detail">
            <!-- Ingestion Details -->
            <template v-if="log.event_type === 'ingest'">
              <div v-for="item in log.details" :key="item.landmark_id" class="detail-section">
                <div class="detail-section-title">
                  地标: <strong>{{ item.landmark_name }}</strong> ({{ item.bangumi }})
                  <span class="chunks-badge">{{ item.chunks_count }} 个切片</span>
                </div>
                
                <div class="detail-chunk-list">
                  <div v-for="(chunk, cIdx) in item.chunks" :key="cIdx" class="detail-chunk-item">
                    <span class="chunk-index">切片 #{{ cIdx + 1 }}</span>
                    <p class="chunk-content-text">{{ chunk }}</p>
                  </div>
                </div>
              </div>
            </template>

            <!-- Recall Details -->
            <template v-else-if="log.event_type === 'recall'">
              <!-- Error logging -->
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
                        <span class="chunk-index">Top #{{ chunk.rank }} (评分: {{ chunk.score === -1 ? '相似度' : chunk.score.toFixed(3) }})</span>
                        <span class="chunk-source-tag">{{ chunk.landmark_name }} - {{ chunk.bangumi }}</span>
                      </div>
                      <p class="chunk-content-text">{{ chunk.content }}</p>
                      <div class="chunk-footer-row" v-if="chunk.source">
                        <span>来源: {{ chunk.source }}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="detail-section">
                  <div class="detail-section-title">注入模型 Prompt 的完整 RAG Context:</div>
                  <pre class="final-context-pre">{{ log.final_context || '(无数据)' }}</pre>
                </div>
              </template>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Refresh, Delete, Search, Files, HelpFilled, ChatLineRound, Loading, Clock, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const activeSubTab = ref('overview')
const landmarks = ref([])
const loadingLandmarks = ref(false)

const queryText = ref('')
const searching = ref(false)
const searched = ref(false)
const recallResults = ref([])

// Logs states
const logs = ref([])
const loadingLogs = ref(false)
const expandedLogIndex = ref(null)

const totalChunks = computed(() => {
  return landmarks.value.reduce((acc, curr) => acc + (curr.chunks_count || 0), 0)
})

async function fetchLandmarks() {
  loadingLandmarks.value = true
  try {
    const response = await fetch('/api/rag/landmarks')
    if (!response.ok) {
      throw new Error(`HTTP 错误: ${response.status}`)
    }
    const data = await response.json()
    landmarks.value = data
  } catch (error) {
    console.error('获取 RAG 地标缓存失败:', error)
    ElMessage.error(`获取 RAG 地标缓存失败: ${error.message}`)
  } finally {
    loadingLandmarks.value = false
  }
}

async function handleClearDatabase() {
  try {
    await ElMessageBox.confirm(
      '确定要清空 RAG 向量数据库吗？清空后已录入的所有地标切片数据均会丢失，在生成规划时需要重新联网搜索。',
      '危险操作确认',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        type: 'warning'
      }
    )
    
    loadingLandmarks.value = true
    const response = await fetch('/api/rag/clear', { method: 'POST' })
    if (!response.ok) {
      throw new Error(`HTTP 错误: ${response.status}`)
    }
    const result = await response.json()
    ElMessage.success(result.message || 'RAG 数据库已清空')
    landmarks.value = []
    recallResults.value = []
    searched.value = false
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清空 RAG 数据库失败:', error)
      ElMessage.error(`清空 RAG 数据库失败: ${error.message}`)
    }
  } finally {
    loadingLandmarks.value = false
  }
}

async function handleSearch() {
  if (!queryText.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  
  searching.value = true
  searched.value = true
  try {
    const response = await fetch(`/api/rag/query?query=${encodeURIComponent(queryText.value.trim())}`)
    if (!response.ok) {
      throw new Error(`HTTP 错误: ${response.status}`)
    }
    const data = await response.json()
    recallResults.value = data
  } catch (error) {
    console.error('RAG 检索与精排测试失败:', error)
    ElMessage.error(`RAG 检索失败: ${error.message}`)
  } finally {
    searching.value = false
  }
}

// Log related functions
async function fetchLogs() {
  loadingLogs.value = true
  expandedLogIndex.value = null
  try {
    const response = await fetch('/api/rag/logs')
    if (!response.ok) {
      throw new Error(`HTTP 错误: ${response.status}`)
    }
    const data = await response.json()
    logs.value = data
  } catch (error) {
    console.error('获取 RAG 运行日志失败:', error)
    ElMessage.error(`获取 RAG 运行日志失败: ${error.message}`)
  } finally {
    loadingLogs.value = false
  }
}

async function handleClearLogs() {
  try {
    await ElMessageBox.confirm(
      '确定要清空 RAG 历史写入与召回日志吗？',
      '确认清空日志',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        type: 'warning'
      }
    )
    
    loadingLogs.value = true
    const response = await fetch('/api/rag/logs/clear', { method: 'POST' })
    if (!response.ok) {
      throw new Error(`HTTP 错误: ${response.status}`)
    }
    const result = await response.json()
    ElMessage.success(result.message || '历史日志已清空')
    logs.value = []
    expandedLogIndex.value = null
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清空 RAG 运行日志失败:', error)
      ElMessage.error(`清空 RAG 运行日志失败: ${error.message}`)
    }
  } finally {
    loadingLogs.value = false
  }
}

function toggleLogExpand(idx) {
  if (expandedLogIndex.value === idx) {
    expandedLogIndex.value = null
  } else {
    expandedLogIndex.value = idx
  }
}

function formatLogTime(ts) {
  if (!ts) return ''
  // 提取时间部分做极简显示，如 12:05:43
  try {
    const parts = ts.split(' ')
    if (parts.length > 1) return parts[1]
    return ts
  } catch {
    return ts
  }
}

function formatScore(score) {
  if (score === null || score === undefined) return '0.000'
  return score.toFixed(3)
}

function getScoreTagType(score) {
  if (score === -1) return 'info'
  if (score >= 0.8) return 'success'
  if (score >= 0.5) return 'warning'
  return 'danger'
}

function formatSource(source) {
  if (!source) return ''
  if (source.startsWith('http://') || source.startsWith('https://')) {
    try {
      const url = new URL(source)
      return url.hostname
    } catch {
      return source
    }
  }
  return source
}

onMounted(() => {
  fetchLandmarks()
})
</script>

<style scoped>
.rag-console {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.console-sub-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-color);
  background: rgba(0, 0, 0, 0.02);
  flex-shrink: 0;
}

.sub-tabs {
  display: flex;
  gap: 8px;
}

.sub-tab {
  padding: 4px 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.sub-tab:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-color);
}

.sub-tab.active {
  background: var(--primary-color);
  color: white;
  font-weight: 500;
}

.sub-actions {
  display: flex;
  gap: 4px;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}

/* Scrollbar styles */
.tab-content::-webkit-scrollbar {
  width: 6px;
}
.tab-content::-webkit-scrollbar-track {
  background: transparent;
}
.tab-content::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}
.tab-content::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.2);
}

/* Loading & Empty states */
.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  text-align: center;
  color: var(--text-secondary);
  min-height: 200px;
}

.loading-state span {
  margin-top: 8px;
  font-size: 12px;
}

.empty-icon {
  color: var(--border-color);
  margin-bottom: 12px;
}

.empty-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
  margin-bottom: 6px;
}

.empty-hint {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.recall-prompt {
  background: rgba(64, 158, 255, 0.03);
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  margin: 10px 0;
  min-height: 180px;
  padding: 20px 16px;
}

/* Stats */
.db-stats {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 10px;
  padding: 0 4px;
}

.db-stats strong {
  color: var(--text-color);
}

/* Landmark Cards */
.landmarks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.landmark-card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  transition: transform 0.2s, box-shadow 0.2s, background-color 0.2s;
}

.landmark-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
  background: rgba(255, 255, 255, 0.6);
}

.lm-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.lm-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-color);
}

.lm-sub {
  display: flex;
  gap: 4px;
  font-size: 11px;
  line-height: 1.3;
}

.lm-bangumi-label {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.lm-bangumi-value {
  color: var(--primary-color);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Search Box */
.search-box {
  margin-bottom: 12px;
}

/* Recall Cards */
.recall-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recall-meta {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  padding: 0 4px;
}

.recall-meta strong {
  color: var(--text-color);
}

.recall-card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: transform 0.2s, box-shadow 0.2s, background-color 0.2s;
}

.recall-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
  background: rgba(255, 255, 255, 0.6);
}

.recall-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.recall-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.recall-rank {
  font-size: 11px;
  font-weight: bold;
  color: var(--primary-color);
  background: rgba(9, 105, 218, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
  flex-shrink: 0;
}

.recall-source-info {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recall-score-tag {
  font-size: 10px;
  padding: 0 5px;
  height: 18px;
  line-height: 18px;
  flex-shrink: 0;
}

.recall-body {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-color);
  background: rgba(0, 0, 0, 0.015);
  border-radius: 4px;
  padding: 6px 8px;
  border: 1px solid rgba(0, 0, 0, 0.02);
}

.recall-text {
  word-break: break-all;
  white-space: pre-wrap;
}

.recall-footer {
  display: flex;
  gap: 4px;
  font-size: 10px;
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-color);
  padding-top: 4px;
}

.source-label {
  flex-shrink: 0;
}

.source-value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

/* Logs Event List */
.logs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  background: var(--card-bg);
  transition: all 0.2s ease;
}

.log-card.ingest {
  border-left: 4px solid #79bbff;
}

.log-card.recall {
  border-left: 4px solid #95d475;
}

.log-card:hover {
  background: rgba(255, 255, 255, 0.65);
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
}

.log-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.log-type-tag {
  flex-shrink: 0;
  height: 20px;
  line-height: 20px;
}

.log-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.log-time {
  font-size: 11px;
  color: var(--text-secondary);
}

.log-arrow {
  font-size: 12px;
  color: var(--text-secondary);
  transition: transform 0.2s ease;
}

.log-arrow.rotated {
  transform: rotate(90deg);
}

.log-detail {
  border-top: 1px solid var(--border-color);
  padding: 12px;
  background: rgba(255, 255, 255, 0.45);
  font-size: 11px;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section-title {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-color);
  margin-bottom: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chunks-badge {
  font-size: 10px;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 5px;
  border-radius: 4px;
}

.detail-chunk-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-chunk-item {
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 10px;
}

.chunk-header-row {
  display: flex;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 4px;
}

.chunk-index {
  color: var(--primary-color);
}

.chunk-source-tag {
  color: var(--text-secondary);
}

.chunk-content-text {
  line-height: 1.5;
  color: var(--text-color);
  white-space: pre-wrap;
  word-break: break-all;
}

.chunk-footer-row {
  font-size: 9.5px;
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-color);
  margin-top: 6px;
  padding-top: 4px;
}

.final-context-pre {
  background: #f6f8fa;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 10.5px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 250px;
  overflow-y: auto;
  color: var(--text-color);
}

.detail-error {
  background: rgba(245, 108, 108, 0.08);
  border: 1px solid rgba(245, 108, 108, 0.2);
  border-radius: 6px;
  padding: 8px 12px;
  display: flex;
  gap: 6px;
}

.error-label {
  font-weight: bold;
  color: #f56c6c;
}

.error-text {
  color: #f56c6c;
}
</style>
