<template>
  <div class="search-panel">
    <div class="search-header">
      <div class="search-header-top">
        <h2 class="app-title">动漫巡礼</h2>
        <el-button text class="settings-btn" @click="store.showAdminPage = true" title="RAG 数据中心">
          <el-icon><Grid /></el-icon>
        </el-button>
        <el-button text class="settings-btn" @click="showSettings = true">
          <el-icon><Setting /></el-icon>
        </el-button>
      </div>
      <p class="app-subtitle">搜索作品，规划你的圣地巡礼路线</p>
    </div>

    <el-dialog v-model="showSettings" title="AI 设置" width="420px" :close-on-click-modal="true" append-to-body>
      <div class="settings-body">
        <div class="settings-section">
          <label class="settings-label">方案</label>
          <el-radio-group v-model="localScheme">
            <el-radio value="cloud">云端方案</el-radio>
            <el-radio value="local">本地方案</el-radio>
            <el-radio value="agent">Python 智能体</el-radio>
          </el-radio-group>
        </div>

        <div class="settings-section">
          <label class="settings-label">接口地址</label>
          <el-input v-model="localUrl" size="small" placeholder="API endpoint URL" :disabled="localScheme === 'agent'" />
        </div>

        <div class="settings-section" v-if="localScheme !== 'agent'">
          <label class="settings-label">API Key</label>
          <el-input v-model="localApiKey" size="small" placeholder="API Key" type="password" show-password />
        </div>

        <div class="settings-section" v-if="localScheme !== 'agent'">
          <label class="settings-label">Model</label>
          <el-input v-model="localModel" size="small" placeholder="Model name" />
        </div>

        <div class="settings-hint" v-if="localScheme === 'agent'">
          💡 使用本地 Python 智能体服务，请确保已在终端启动 uvicorn。大模型与 Tavily 密钥通过本地 .env 配置。
        </div>
      </div>
      <template #footer>
        <el-button size="small" @click="showSettings = false">取消</el-button>
        <el-button size="small" type="primary" @click="handleConfirm">确认</el-button>
      </template>
    </el-dialog>

    <div class="search-input-group">
      <el-input
        v-model="searchText"
        placeholder="作品名称 或 Bangumi ID"
        size="large"
        @keyup.enter="handleSearch"
        @input="handleInput"
        :disabled="loading"
        clearable
        @clear="handleClear"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <div v-if="searchResults.length > 0" class="search-results">
      <div class="results-header">
        <span>搜索结果 ({{ searchResults.length }})</span>
        <el-button text size="small" @click="store.clearSearchResults()">关闭</el-button>
      </div>
      <div class="results-list scrollbar-wrapper">
        <div
          v-for="item in searchResults"
          :key="item.id"
          class="result-item"
          @click="handleSelectResult(item)"
        >
          <div class="result-cover" v-if="item.image">
            <img :src="item.image" :alt="item.name_cn || item.name" loading="lazy" />
          </div>
          <div class="result-cover placeholder" v-else>
            <el-icon :size="20"><Picture /></el-icon>
          </div>
          <div class="result-info">
            <div class="result-name">{{ item.name_cn || item.name }}</div>
            <div v-if="item.name_cn && item.name !== item.name_cn" class="result-original">{{ item.name }}</div>
            <div class="result-meta">
              <span v-if="item.air_date">放送: {{ item.air_date }}</span>
              <span class="result-id">ID: {{ item.id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-message">
      <el-alert :title="error" type="error" show-icon :closable="false" />
    </div>

    <div v-if="bangumi" class="bangumi-info">
      <div class="bangumi-cover-wrapper">
        <img :src="bangumi.cover" :alt="bangumi.cn" class="bangumi-cover" />
      </div>
      <div class="bangumi-details">
        <h3 class="bangumi-title">{{ bangumi.cn || bangumi.title }}</h3>
        <p v-if="bangumi.title !== bangumi.cn" class="bangumi-original-title">{{ bangumi.title }}</p>
        <div class="bangumi-meta">
          <el-tag v-if="bangumi.city" size="small" effect="dark">{{ bangumi.city }}</el-tag>
          <el-tag size="small" effect="plain">{{ points.length }} 个地标</el-tag>
          <el-tag size="small" type="info">ID: {{ bangumi.id }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Picture, Setting, Grid } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'

const store = useAppStore()
const { bangumi, points, loading, error, searchResults } = storeToRefs(store)

const searchText = ref('')
let searchTimer = null

const showSettings = ref(false)
const localScheme = ref(store.aiConfig?.scheme || 'cloud')
const activeCfg = store.activeAiConfig || store.aiConfig?.cloud || { url: '', apiKey: '', model: '' }
const localUrl = ref(activeCfg.url)
const localApiKey = ref(activeCfg.apiKey)
const localModel = ref(activeCfg.model)

watch(showSettings, (val) => {
  if (val) {
    localScheme.value = store.aiConfig?.scheme || 'cloud'
    const active = store.activeAiConfig || store.aiConfig?.cloud || {}
    localUrl.value = active.url || ''
    localApiKey.value = active.apiKey || ''
    localModel.value = active.model || ''
  }
})

watch(localScheme, (scheme) => {
  const cfg = store.aiConfig?.[scheme]
  if (cfg) {
    localUrl.value = cfg.url || ''
    localApiKey.value = cfg.apiKey || ''
    localModel.value = cfg.model || ''
  }
})

function handleConfirm() {
  const scheme = localScheme.value
  const cfg = store.aiConfig
  cfg.scheme = scheme
  cfg[scheme].url = localUrl.value
  cfg[scheme].apiKey = localApiKey.value
  cfg[scheme].model = localModel.value
  store.saveAiConfig()
  showSettings.value = false
}

function handleInput(val) {
  if (searchTimer) clearTimeout(searchTimer)
  if (!val || !val.trim()) {
    store.clearSearchResults()
    return
  }
  if (/^\d+$/.test(val.trim())) {
    store.clearSearchResults()
    return
  }
  searchTimer = setTimeout(() => {
    store.searchByKey(val)
  }, 500)
}

async function handleSearch() {
  if (!searchText.value) return
  const text = searchText.value.trim()
  if (/^\d+$/.test(text)) {
    store.clearSearchResults()
    await store.searchBangumi(text)
  } else {
    await store.searchByKey(text)
  }
}

async function handleSelectResult(item) {
  searchText.value = String(item.id)
  store.clearSearchResults()
  await store.searchBangumi(item.id)
}

function handleClear() {
  store.clearSearchResults()
}
</script>

<style scoped>
.search-panel {
  padding: 28px 24px 20px;
  border-bottom: 1px solid var(--border-color);
}

.search-header {
  margin-bottom: 24px;
}

.app-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary-color);
  letter-spacing: 1px;
}

.search-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.settings-btn {
  color: var(--text-secondary) !important;
  font-size: 16px;
}

.settings-btn:hover {
  color: var(--primary-color) !important;
}

.settings-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.settings-hint {
  font-size: 11px;
  color: var(--text-secondary);
  text-align: center;
  padding-top: 4px;
  border-top: 1px solid var(--border-color);
}

.app-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.search-input-group {
  display: flex;
  gap: 8px;
}

.search-input-group .el-input {
  flex: 1;
}

.search-results {
  margin-top: 12px;
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}

.results-list {
  max-height: 260px;
  overflow-y: auto;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.result-item:last-child {
  border-bottom: none;
}

.result-item:hover {
  background-color: rgba(9, 105, 218, 0.08);
}

.result-cover {
  flex-shrink: 0;
  width: 44px;
  height: 60px;
  border-radius: 4px;
  overflow: hidden;
  background-color: var(--bg-color);
}

.result-cover.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.result-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.result-info {
  flex: 1;
  min-width: 0;
}

.result-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.result-original {
  font-size: 11px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.result-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.result-id {
  color: var(--primary-color);
  opacity: 0.7;
}

.error-message {
  margin-top: 12px;
}

.bangumi-info {
  display: flex;
  gap: 14px;
  margin-top: 16px;
  padding: 14px;
  background-color: var(--card-bg);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.bangumi-cover-wrapper {
  flex-shrink: 0;
  width: 80px;
  height: 110px;
  border-radius: 6px;
  overflow: hidden;
}

.bangumi-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bangumi-details {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-width: 0;
}

.bangumi-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bangumi-original-title {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bangumi-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
