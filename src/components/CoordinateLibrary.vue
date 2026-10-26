<template>
  <div class="coordinate-library">
    <header class="library-header">
      <h1>{{ activeTab === 'library' ? '我的巡礼清单' : '旅途档案' }}</h1>
      <p>
        {{
          activeTab === 'library'
            ? '管理已收藏的取景地标，由 AI 规划多日行程'
            : '回顾已生成的巡礼路线与历史规划记录'
        }}
      </p>
    </header>

    <!-- 坐标库 -->
    <template v-if="activeTab === 'library'">
      <div v-if="coordinateLibrary.length === 0 && !currentPlan" class="lib-empty">
        <div class="empty-illustration">
          <AppIcon name="bookmark" :size="28" />
        </div>
        <h2>暂无收藏地标</h2>
        <p>在探索面板或地图上收藏感兴趣的地标后，即可在此规划行程。</p>
        <button class="primary-button" @click="emit('explore')">
          去发现圣地
          <AppIcon name="arrow" :size="16" />
        </button>
      </div>

      <template v-else>
        <div class="lib-body-scroll">
          <div v-if="coordinateLibrary.length" class="lib-toolbar">
            <el-checkbox
              :model-value="
                coordinateLibrary.length > 0 &&
                coordinateLibrary.every((e) => e.checked)
              "
              :indeterminate="
                librarySelected.length > 0 &&
                librarySelected.length < coordinateLibrary.length
              "
              @change="handleCheckAll"
              @click.stop
            >
              全选
            </el-checkbox>
            <div class="lib-toolbar-actions">
              <span class="selection-count">
                已选 {{ librarySelected.length }} / {{ coordinateLibrary.length }}
              </span>
              <el-button
                text
                size="small"
                type="danger"
                :disabled="librarySelected.length === 0"
                @click.stop="handleRemoveSelected"
              >
                移除
              </el-button>
            </div>
          </div>

          <div v-if="coordinateLibrary.length" class="lib-list">
            <div
              v-for="entry in coordinateLibrary"
              :key="entry.id"
              class="lib-item"
              :class="{ unchecked: !entry.checked }"
            >
              <el-checkbox
                :model-value="entry.checked"
                :aria-label="`将 ${entry.name} 纳入行程`"
                @change="store.toggleLibraryItem(entry.id)"
                @click.stop
              />
              <div class="lib-thumb" v-if="entry.image">
                <img
                  :src="getThumbUrl(entry.image)"
                  :alt="entry.name"
                  referrerpolicy="no-referrer"
                  loading="lazy"
                />
              </div>
              <div class="lib-thumb placeholder" v-else>
                <el-icon :size="15"><Star /></el-icon>
              </div>
              <button class="lib-info" @click="focusLandmark(entry)">
                <div class="lib-name">{{ entry.name }}</div>
                <div class="lib-source" v-if="entry.bangumiName">
                  {{ entry.bangumiName }}
                </div>
                <div v-if="!hasValidGeo(entry)" class="lib-missing-geo">
                  缺少坐标，无法参与路线规划
                </div>
              </button>
              <el-button
                text
                size="small"
                class="lib-remove-btn"
                :aria-label="`移除 ${entry.name}`"
                @click.stop="store.removeFromLibrary(entry.id)"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
          </div>

          <div v-if="coordinateLibrary.length" class="lib-controls">
            <div class="planner-heading">
              <div class="planner-title">
                <AppIcon name="sparkles" :size="16" />
                <strong>AI 路线规划</strong>
              </div>
              <button
                class="planner-settings text-button"
                @click="store.settingsOpen = true"
              >
                {{ getSchemeLabel(store.aiConfig.scheme) }}
                <AppIcon name="settings" :size="13" />
              </button>
            </div>
            <div class="lib-days-row">
              <span class="lib-label">出行天数</span>
              <el-input-number
                v-model="libraryDays"
                :min="1"
                :max="7"
                size="small"
                aria-label="巡礼天数"
                :disabled="librarySelected.length === 0"
              />
            </div>
            <el-button
              type="primary"
              @click="handleGenerate"
              :loading="planning"
              :disabled="librarySelected.length === 0 || (loading && !planning)"
            >
              <AppIcon v-if="!planning" name="sparkles" :size="15" />
              {{ planning ? '正在编排旅程…' : '生成巡礼路线' }}
            </el-button>
          </div>

          <div v-if="!coordinateLibrary.length && currentPlan" class="plan-no-library">
            历史行程已从保存的地标快照恢复。
            <button class="text-button" @click="emit('explore')">继续发现地标</button>
          </div>

          <div v-if="store.error && !planning" class="lib-ai-error">
            <el-alert
              :title="store.error"
              type="error"
              show-icon
              :closable="false"
            />
          </div>
          <div v-if="store.historySaveError" class="lib-ai-error">
            <el-alert :title="store.historySaveError" type="warning" show-icon :closable="false" />
          </div>
          <div v-if="planning && store.planningProgress" class="plan-progress" role="status">
            <el-icon class="is-loading" :size="16"><Loading /></el-icon>
            <span>{{ store.planningProgress }}</span>
            <button class="text-button" @click="store.cancelLibraryItinerary()">取消</button>
          </div>
          <PlanResult
            v-if="currentPlan"
            :plan="currentPlan"
            :landmarks="generatedLandmarks"
            @select-point="focusPlanPoint"
          />
          <div v-if="libraryAiResponse || (planning && !store.planningProgress)" class="lib-ai-response">
            <div class="lib-ai-header">
              <span class="lib-ai-badge">AI 行程说明</span>
              <div class="lib-ai-header-actions">
                <el-button
                  v-if="parsedAiResponse.cleanMarkdown"
                  text
                  size="small"
                  class="lib-expand-btn"
                  @click="
                    openExpandedView(
                      'AI 路线规划详情',
                      generatedLandmarks,
                      parsedAiResponse.cleanMarkdown
                    )
                  "
                >
                  <el-icon><FullScreen /></el-icon>
                  展开
                </el-button>
                <el-button
                  v-if="parsedAiResponse.cleanMarkdown"
                  text
                  size="small"
                  class="lib-copy-btn"
                  @click="handleCopy"
                >
                  <el-icon><DocumentCopy /></el-icon>
                  {{ copied ? '已复制' : '复制' }}
                </el-button>
              </div>
            </div>

            <!-- AI Planning Timeline Steps Loader -->
            <div
              v-if="planning && !parsedAiResponse.cleanMarkdown && !store.planningProgress"
              class="ai-status-loader"
            >
              <div class="status-spinner-row">
                <el-icon class="is-loading" :size="18"><Loading /></el-icon>
                <span class="status-title">AI 正在规划中...</span>
              </div>
              <div class="status-steps">
                <div
                  class="status-step"
                  :class="{
                    active:
                      parsedAiResponse.currentStatus &&
                      (parsedAiResponse.currentStatus.startsWith(
                        '正在进行信息检索与验证'
                      ) ||
                        parsedAiResponse.currentStatus.startsWith(
                          '正在检索与验证地标'
                        )),
                    completed: isStepCompleted('正在进行信息检索与验证...')
                  }"
                >
                  <span class="step-dot"></span>
                  <span class="step-text">信息检索与数据补全</span>
                </div>
                <div
                  class="status-step"
                  :class="{
                    active:
                      parsedAiResponse.currentStatus &&
                      parsedAiResponse.currentStatus.startsWith(
                        '正在根据地理区域和天气进行路线规划'
                      ),
                    completed: isStepCompleted(
                      '正在根据地理区域和天气进行路线规划...'
                    )
                  }"
                >
                  <span class="step-dot"></span>
                  <span class="step-text">安排路线与交通</span>
                </div>
                <div
                  class="status-step"
                  :class="{
                    active:
                      parsedAiResponse.currentStatus &&
                      parsedAiResponse.currentStatus.startsWith(
                        '正在匹配动漫原作场景时段与拍照建议'
                      ),
                    completed: isStepCompleted(
                      '正在匹配动漫原作场景时段与拍照建议...'
                    )
                  }"
                >
                  <span class="step-dot"></span>
                  <span class="step-text">动漫原作场景还原匹配</span>
                </div>
                <div
                  class="status-step"
                  :class="{
                    active:
                      parsedAiResponse.currentStatus &&
                      parsedAiResponse.currentStatus.includes(
                        '正在进行路线合理性审查与微调'
                      ),
                    completed:
                      isStepCompleted('正在进行路线合理性审查与微调...')
                  }"
                >
                  <span class="step-dot"></span>
                  <span class="step-text">检查行程与整理</span>
                </div>
              </div>
              <div
                v-if="parsedAiResponse.currentStatus"
                class="status-current-detail"
              >
                {{ parsedAiResponse.currentStatus }}
              </div>
            </div>

            <!-- Clean Markdown content once generated -->
            <div
              v-if="parsedAiResponse.cleanMarkdown"
              class="lib-ai-content"
              v-html="renderMarkdown(parsedAiResponse.cleanMarkdown)"
            ></div>
          </div>
        </div>
      </template>
    </template>

    <!-- 历史记录 -->
    <template v-if="activeTab === 'history'">
      <div v-if="routeHistory.length === 0" class="lib-empty">
        <div class="empty-illustration">
          <AppIcon name="clock" :size="28" />
        </div>
        <h2>暂无旅途档案</h2>
        <p>生成的巡礼路线会自动保存在这里，方便随时查看。</p>
        <button class="primary-button" @click="store.activePanel = 'library'">
          去规划行程
          <AppIcon name="arrow" :size="16" />
        </button>
      </div>

      <template v-else>
        <div class="lib-toolbar">
          <span class="lib-history-count">
            共 {{ routeHistory.length }} 条记录
          </span>
          <div class="lib-toolbar-actions">
            <el-button text size="small" type="danger" @click="handleClearAll">
              清空全部
            </el-button>
          </div>
        </div>

        <div class="history-list scrollbar-wrapper">
          <div
            v-for="record in routeHistory"
            :key="record.id"
            class="history-item"
          >
            <div
              class="history-header"
              role="button"
              tabindex="0"
              :aria-expanded="expandedId === record.id"
              @click="toggleExpand(record)"
              @keydown.enter.self="toggleExpand(record)"
              @keydown.space.self.prevent="toggleExpand(record)"
            >
              <div class="history-info">
                <div class="history-title-row">
                  <span class="history-time">
                    {{ formatTimestamp(record.timestamp) }}
                  </span>
                  <span :class="['scheme-badge', record.scheme || 'cloud']">
                    {{ getSchemeLabel(record.scheme) }}
                  </span>
                </div>
                <span class="history-meta">
                  {{ record.days }} 天 ·
                  {{ (record.landmarkSnapshot || record.landmarks || []).length }} 个地点
                </span>
              </div>
              <div class="history-actions">
                <el-button
                  text
                  size="small"
                  type="danger"
                  @click.stop="handleDelete(record.id)"
                >
                  删除
                </el-button>
                <el-icon
                  class="history-arrow"
                  :class="{ rotated: expandedId === record.id }"
                >
                  <ArrowDown />
                </el-icon>
              </div>
            </div>

            <div v-if="expandedId === record.id" class="history-body">
              <PlanResult
                v-if="record.plan"
                :plan="record.plan"
                :landmarks="record.landmarkSnapshot || record.plan.request_snapshot?.landmarks || []"
                @select-point="focusPlanPoint"
              />
              <div
                v-if="!record.plan && expandedCache[record.id]?.loading"
                class="history-loading"
              >
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载地标信息...</span>
              </div>
              <template v-else-if="!record.plan && expandedCache[record.id]?.landmarkList">
                <div class="history-landmarks">
                  <div class="history-section-title">地标列表</div>
                  <div
                    v-for="(pt, idx) in expandedCache[record.id].landmarkList"
                    :key="pt.id"
                    class="history-landmark-item"
                    role="button"
                    tabindex="0"
                    :aria-label="`在地图查看 ${pt.cn || pt.name || pt.id}`"
                    @click="focusPlanPoint(pt)"
                    @keydown.enter.self="focusPlanPoint(pt)"
                    @keydown.space.self.prevent="focusPlanPoint(pt)"
                  >
                    <span class="hl-index">{{ idx + 1 }}</span>
                    <div class="hl-info">
                      <span class="hl-name">
                        {{ pt.cn || pt.name || pt.id }}
                      </span>
                      <span class="hl-meta" v-if="pt.ep || pt.s">
                        <template v-if="pt.ep">EP{{ pt.ep }}</template>
                        <template v-if="pt.s"> · {{ formatSeconds(pt.s) }}</template>
                      </span>
                    </div>
                    <el-icon class="hl-go" @click.stop="showHistoryImage(pt)">
                      <View />
                    </el-icon>
                  </div>
                </div>
              </template>

              <div
                v-if="!record.plan && expandedCache[record.id]?.failedCount"
                class="history-failed-warn"
              >
                注意：{{ expandedCache[record.id].failedCount }} 个地标信息加载失败
              </div>

              <div class="history-ai-response" v-if="record.aiResponse">
                <div class="history-section-title-row">
                  <div class="history-section-title">AI 回复</div>
                  <el-button
                    text
                    size="small"
                    class="lib-expand-btn"
                    @click="
                      openExpandedView(
                        '历史路线规划',
                        (expandedCache[record.id]?.landmarkList || []).map(
                          (p) => ({
                            id: p.id,
                            name: p.cn || p.name || p.id,
                            image: p.image || '',
                            bangumiName: p.bangumiName || ''
                          })
                        ),
                        record.aiResponse
                      )
                    "
                  >
                    <el-icon><FullScreen /></el-icon>
                    展开
                  </el-button>
                </div>
                <div
                  class="lib-ai-content"
                  v-html="renderMarkdown(record.aiResponse)"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>

  <el-dialog
    v-model="historyImageDialog"
    :title="historyImageName"
    width="420px"
    :close-on-click-modal="true"
    destroy-on-close
    append-to-body
  >
    <div v-if="historyImageUrl">
      <div class="history-image-wrapper">
        <img
          :src="getImageUrl(historyImageUrl, 'h360')"
          :alt="historyImageName"
          referrerpolicy="no-referrer"
          class="history-image"
        />
      </div>
      <div class="history-compare-row">
        <button class="history-compare-btn" @click="handleHistoryCompare">
          取景对比
        </button>
      </div>
    </div>
    <div v-else class="history-image-empty">
      <el-icon :size="32"><Picture /></el-icon>
      <span>暂无图片</span>
    </div>
  </el-dialog>

  <!-- 展开查看 AI 路线规划 -->
  <el-dialog
    v-model="expandedView.visible"
    :title="expandedView.title"
    :fullscreen="true"
    :close-on-click-modal="true"
    destroy-on-close
    append-to-body
  >
    <div class="expanded-view">
      <div class="expanded-left">
        <h4>巡礼地标 ({{ expandedView.landmarks.length }})</h4>
        <div class="expanded-landmark-list">
          <div
            v-for="lm in expandedView.landmarks"
            :key="lm.id"
            class="expanded-landmark-item"
          >
            <div class="expanded-thumb" v-if="lm.image">
              <img
                :src="getImageUrl(lm.image, 'h360')"
                :alt="lm.name"
                referrerpolicy="no-referrer"
                loading="lazy"
              />
            </div>
            <div class="expanded-thumb placeholder" v-else>
              <el-icon :size="20"><Picture /></el-icon>
            </div>
            <div class="expanded-lm-info">
              <div class="expanded-lm-name">{{ lm.name }}</div>
              <div class="expanded-lm-bangumi">{{ lm.bangumiName }}</div>
            </div>
          </div>
        </div>
      </div>
      <div class="expanded-right">
        <div
          class="lib-ai-content"
          v-html="renderMarkdown(expandedView.markdown)"
        ></div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import {
  Star,
  Close,
  ArrowDown,
  DocumentCopy,
  Loading,
  View,
  Picture,
  FullScreen
} from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppIcon from './AppIcon.vue'
import PlanResult from './PlanResult.vue'
import { fetchBangumiLite, fetchBangumiPointsDetail } from '../utils/api'
import { getImageUrl } from '../utils/imageUrl'

const store = useAppStore()
const {
  coordinateLibrary,
  librarySelected,
  libraryAiResponse,
  loading,
  planning,
  routeHistory,
  generatedLandmarks,
  currentPlan
} = storeToRefs(store)
const emit = defineEmits(['explore', 'show-map'])

const copied = ref(false)
const expandedView = reactive({
  visible: false,
  title: '',
  landmarks: [],
  markdown: ''
})

function openExpandedView(title, landmarks, markdown) {
  expandedView.title = title
  expandedView.landmarks = landmarks
  expandedView.markdown = markdown
  expandedView.visible = true
}

const statusSteps = [
  '正在进行信息检索与验证...',
  '正在根据地理区域和天气进行路线规划...',
  '正在匹配动漫原作场景时段与拍照建议...',
  '正在进行路线合理性审查与微调...'
]

const parsedAiResponse = computed(() => {
  const text = libraryAiResponse.value || ''
  const lines = text.split('\n')
  const statusLines = []
  const markdownLines = []

  for (const line of lines) {
    if (line.startsWith('__STATUS__:')) {
      statusLines.push(line.replace('__STATUS__:', '').trim())
    } else {
      markdownLines.push(line)
    }
  }

  const currentStatus =
    statusLines.length > 0 ? statusLines[statusLines.length - 1] : ''
  const cleanMarkdown = markdownLines.join('\n').trim()

  return {
    currentStatus,
    cleanMarkdown
  }
})

function isStepCompleted(stepPrefix) {
  const text = libraryAiResponse.value || ''
  if (parsedAiResponse.value.cleanMarkdown) return true

  const current = parsedAiResponse.value.currentStatus
  if (!current) return false

  const rawStatusList = text
    .split('\n')
    .filter((l) => l.startsWith('__STATUS__:'))

  const currentIndex = statusSteps.findIndex((s) =>
    current.startsWith(s.slice(0, 10))
  )
  const stepIndex = statusSteps.findIndex((s) =>
    s.startsWith(stepPrefix.slice(0, 10))
  )

  if (stepIndex === -1) return false

  if (currentIndex > stepIndex) return true

  const hasStep = rawStatusList.some((line) =>
    line.includes(stepPrefix.slice(0, 15))
  )
  const isLast = current.startsWith(stepPrefix.slice(0, 15))
  if (hasStep && !isLast) return true

  return false
}

function getSchemeLabel(scheme) {
  if (!scheme) return '云端方案'
  switch (scheme) {
    case 'cloud':
      return '云端方案'
    case 'local':
      return '本地方案'
    case 'agent':
      return 'Python 智能体'
    default:
      return '未知方案'
  }
}

function hasValidGeo(entry) {
  return (
    Array.isArray(entry.geo) &&
    entry.geo.length === 2 &&
    entry.geo.every(Number.isFinite) &&
    Math.abs(entry.geo[0]) <= 90 &&
    Math.abs(entry.geo[1]) <= 180
  )
}

const libraryDays = storeToRefs(store).libraryDays

const activeTab = computed(() =>
  store.activePanel === 'history' ? 'history' : 'library'
)
const expandedId = ref(null)
const expandedCache = reactive({})

const historyImageDialog = ref(false)
const historyImageUrl = ref('')
const historyImageName = ref('')

function showHistoryImage(pt) {
  historyImageUrl.value = pt.image || ''
  historyImageName.value = pt.cn || pt.name || pt.id
  historyImageDialog.value = true
}

function handleHistoryCompare() {
  historyImageDialog.value = false
  store.compareData = {
    image: historyImageUrl.value,
    name: historyImageName.value
  }
}

function toggleExpand(record) {
  if (expandedId.value === record.id) {
    expandedId.value = null
    return
  }
  expandedId.value = record.id
  store.restoreRouteHistory(record, expandedCache[record.id]?.landmarkList || [])
  if (record.plan) {
    expandedCache[record.id] = {
      loading: false,
      landmarkList: record.landmarkSnapshot || record.plan.request_snapshot?.landmarks || [],
      failedCount: 0
    }
    return
  }
  if (expandedCache[record.id]) return
  expandedCache[record.id] = { loading: true, landmarkList: [] }
  loadHistoryDetail(record)
}

async function loadHistoryDetail(record) {
  const groups = {}
  record.landmarks.forEach((lm) => {
    if (!groups[lm.bangumiId]) groups[lm.bangumiId] = []
    groups[lm.bangumiId].push(lm.id)
  })

  const landmarkList = []
  let failedCount = 0
  let missedCount = 0
  for (const [bangumiId, pointIds] of Object.entries(groups)) {
    try {
      const [liteData, detailData] = await Promise.all([
        fetchBangumiLite(bangumiId),
        fetchBangumiPointsDetail(bangumiId, true)
      ])
      const bangumiName = liteData.cn || liteData.title || ''
      const bangumiOriginalName = liteData.title || ''
      pointIds.forEach((pid) => {
        const p = detailData.find((d) => d.id === pid)
        if (p) {
          landmarkList.push({
            ...p,
            bangumiName,
            bangumiOriginalName,
            bangumiId
          })
        } else {
          missedCount++
        }
      })
    } catch {
      failedCount += pointIds.length
    }
  }

  if (expandedCache[record.id]) {
    expandedCache[record.id].landmarkList = landmarkList
    expandedCache[record.id].loading = false
    expandedCache[record.id].failedCount = failedCount + missedCount
    if (expandedId.value === record.id) store.historyLandmarks = landmarkList
  }
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定要删除这条历史记录吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    store.deleteRouteHistory(id)
    if (expandedId.value === id) expandedId.value = null
    delete expandedCache[id]
    ElMessage.success('已删除')
  } catch {}
}

async function handleClearAll() {
  try {
    await ElMessageBox.confirm('确定要清空所有历史记录吗？', '确认清空', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning'
    })
    store.clearRouteHistory()
    expandedId.value = null
    Object.keys(expandedCache).forEach((k) => delete expandedCache[k])
    ElMessage.success('已清空历史记录')
  } catch {}
}

function formatTimestamp(ts) {
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatSeconds(seconds) {
  if (!seconds && seconds !== 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0)
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function handleCheckAll(val) {
  if (val) store.libraryCheckAll()
  else store.libraryUncheckAll()
}

function focusLandmark(entry) {
  store.selectPoint(entry.id)
  emit('show-map')
}

function focusPlanPoint(point) {
  if (!hasValidGeo(point)) {
    ElMessage.warning('该地标缺少有效坐标，无法在地图上定位')
    return
  }
  store.selectPoint(point.id)
  emit('show-map')
}

async function handleGenerate() {
  await store.generateLibraryItinerary()
}

async function handleRemoveSelected() {
  if (librarySelected.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${librarySelected.value.length} 个坐标吗？`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    store.libraryRemoveSelected()
    ElMessage.success('已删除选中的坐标')
  } catch {}
}

async function handleCopy() {
  const textToCopy = parsedAiResponse.value.cleanMarkdown
  if (!textToCopy) return
  try {
    await navigator.clipboard.writeText(textToCopy)
    copied.value = true
    ElMessage.success('路线规划已复制到剪贴板')
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

function getThumbUrl(imageUrl) {
  return getImageUrl(imageUrl, 'h160')
}

function renderMarkdown(text) {
  if (!text) return ''

  const cleanText = text
    .split('\n')
    .filter((line) => !line.startsWith('__STATUS__:'))
    .join('\n')

  const escaped = cleanText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  let html = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  const blocks = html.split(/\n\n+/)
  const out = blocks.map((block) => {
    block = block.trim()
    if (!block) return ''

    if (/^### /.test(block)) {
      const nl = block.indexOf('\n')
      if (nl === -1) return `<h4>${block.slice(4)}</h4>`
      return `<h4>${block.slice(4, nl)}</h4><p>${block.slice(nl + 1).trim()}</p>`
    }
    if (/^## /.test(block)) {
      const nl = block.indexOf('\n')
      if (nl === -1) return `<h3>${block.slice(3)}</h3>`
      return `<h3>${block.slice(3, nl)}</h3><p>${block.slice(nl + 1).trim()}</p>`
    }
    if (/^# /.test(block)) {
      const nl = block.indexOf('\n')
      if (nl === -1) return `<h2>${block.slice(2)}</h2>`
      return `<h2>${block.slice(2, nl)}</h2><p>${block.slice(nl + 1).trim()}</p>`
    }

    const lines = block.split('\n')

    if (lines.every((l) => /^\- /.test(l))) {
      return (
        '<ul>' + lines.map((l) => `<li>${l.slice(2)}</li>`).join('') + '</ul>'
      )
    }

    if (lines.every((l) => /^\d+\.\s/.test(l))) {
      return (
        '<ol>' +
        lines.map((l) => `<li>${l.replace(/^\d+\.\s*/, '')}</li>`).join('') +
        '</ol>'
      )
    }

    return `<p>${lines.filter((l) => l.trim()).join('<br>')}</p>`
  })

  return out.filter(Boolean).join('\n')
}
</script>

<style scoped>
.coordinate-library {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.library-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 16px;
  flex-shrink: 0;
}

.library-header h1 {
  font-size: 19px;
  font-weight: 600;
  color: var(--text-color);
  letter-spacing: 0.3px;
}

.library-header p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.lib-empty {
  display: flex;
  flex: 1;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  color: var(--text-secondary);
  text-align: center;
}

.empty-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  background: var(--primary-soft);
  border-radius: 18px;
  color: var(--primary-color);
  margin-bottom: 18px;
}

.lib-empty h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
  margin-bottom: 8px;
}

.lib-empty p {
  font-size: 13px;
  line-height: 1.6;
  max-width: 240px;
}

.lib-empty .primary-button {
  margin-top: 20px;
}

.lib-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 12px;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.lib-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selection-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.lib-toolbar :deep(.el-checkbox__label) {
  font-size: 13px;
  color: var(--text-color);
}

.lib-list {
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lib-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 10px;
  transition:
    background 0.18s ease,
    opacity 0.18s ease;
}

.lib-item:hover {
  background-color: rgba(255, 255, 255, 0.7);
}

.lib-item.unchecked {
  opacity: 0.45;
}

.lib-thumb {
  flex-shrink: 0;
  width: 56px;
  height: 42px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.05);
}

.lib-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.lib-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.lib-info {
  flex: 1;
  min-width: 0;
  border: 0;
  padding: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.lib-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.lib-source {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.lib-missing-geo {
  margin-top: 4px;
  color: #d97706;
  font-size: 12px;
}

.lib-remove-btn {
  flex-shrink: 0;
  opacity: 0.5;
  transition: opacity 0.2s;
  padding: 4px !important;
  height: 28px !important;
}

.lib-item:hover .lib-remove-btn,
.lib-remove-btn:focus-visible {
  opacity: 0.85;
}

.lib-remove-btn:hover {
  opacity: 1 !important;
  color: var(--el-color-danger) !important;
}

.lib-controls {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  margin: 12px 0;
}

.planner-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.planner-title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--primary-color);
  font-size: 14px;
}

.planner-settings {
  font-size: 12px;
}

.lib-days-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}

.lib-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.lib-controls :deep(.el-input-number) {
  width: 110px;
}

.lib-controls > .el-button {
  min-height: 40px;
  width: 100%;
  font-size: 14px;
}

.lib-controls > .el-button :deep(span) {
  gap: 6px;
}

.lib-body-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-right: 4px;
  overscroll-behavior: contain;
}

.lib-ai-response {
  padding: 16px 0 8px;
  border-top: 1px solid var(--border-color);
  margin-top: 16px;
}

.lib-ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.lib-ai-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
  background: var(--primary-soft);
}

.lib-ai-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.lib-copy-btn,
.lib-expand-btn {
  color: var(--text-secondary) !important;
  transition: color 0.2s;
}

.lib-copy-btn:hover,
.lib-expand-btn:hover {
  color: var(--primary-color) !important;
}

.lib-ai-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-color);
  overflow-wrap: anywhere;
}

.lib-ai-content :deep(h2) {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 6px;
  color: var(--text-color);
}

.lib-ai-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 10px 0 4px;
  color: var(--text-color);
}

.lib-ai-content :deep(h4) {
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: var(--text-color);
}

.lib-ai-content :deep(p) {
  margin: 0 0 8px;
}

.lib-ai-content :deep(strong) {
  color: var(--primary-color);
  font-weight: 600;
}

.lib-ai-content :deep(ul),
.lib-ai-content :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.lib-ai-content :deep(li) {
  margin: 2px 0;
}

/* History */
.lib-history-count {
  font-size: 13px;
  color: var(--text-secondary);
}

.history-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  padding: 12px 4px 12px 0;
}

.history-item {
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  overflow: hidden;
  margin-bottom: 10px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  gap: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.history-header:hover {
  background-color: rgba(255, 255, 255, 0.92);
}

.history-header:focus-visible {
  outline-offset: -3px;
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-time {
  font-size: 13px;
  color: var(--text-color);
  font-weight: 600;
}

.history-meta {
  font-size: 12px;
  color: var(--text-secondary);
}

.history-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.history-arrow {
  font-size: 14px;
  color: var(--text-secondary);
  transition: transform 0.18s ease;
}

.history-arrow.rotated {
  transform: rotate(180deg);
}

.history-body {
  border-top: 1px solid var(--border-color);
  padding: 12px 14px;
}

.history-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 13px;
}

.history-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.history-section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.history-landmarks {
  margin-bottom: 12px;
}

.history-landmark-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.history-landmark-item:hover {
  background-color: var(--primary-soft);
}

.hl-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary-color);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
}

.hl-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.hl-name {
  font-size: 13px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hl-meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.hl-go {
  font-size: 15px;
  color: var(--text-secondary);
  opacity: 0;
  transition: opacity 0.15s;
}

.history-landmark-item:hover .hl-go {
  opacity: 0.8;
}

.history-ai-response {
  margin-top: 8px;
}

.history-image-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
}

.history-compare-row {
  display: flex;
  justify-content: center;
  padding: 12px 0 4px;
}

.history-compare-btn {
  padding: 6px 16px;
  border: 1px solid rgba(37, 99, 235, 0.25);
  background: var(--primary-soft);
  color: var(--primary-color);
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.history-compare-btn:hover {
  background: var(--primary-color);
  color: #ffffff;
}

.history-image {
  max-width: 100%;
  max-height: 60vh;
  border-radius: 10px;
  object-fit: contain;
}

.history-image-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px;
  color: var(--text-secondary);
  font-size: 13px;
}

.scheme-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 6px;
  font-weight: 500;
  line-height: 1.3;
}

.scheme-badge.cloud {
  background-color: var(--primary-soft);
  color: var(--primary-color);
}

.scheme-badge.local {
  background-color: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.scheme-badge.agent {
  background-color: rgba(16, 185, 129, 0.12);
  color: #059669;
}

/* AI Stream Planning progress status loader styling */
.ai-status-loader {
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: rgba(255, 255, 255, 0.65);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  margin: 12px 0;
}

.status-spinner-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.status-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.status-steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
  padding-left: 20px;
  margin-bottom: 12px;
}

.status-steps::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: var(--border-color);
  z-index: 1;
}

.status-step {
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
  z-index: 2;
}

.step-dot {
  position: absolute;
  left: -20px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #ffffff;
  border: 2px solid var(--border-color);
  transition: all 0.3s ease;
}

.step-text {
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.3s ease;
}

.status-step.active .step-dot {
  border-color: var(--primary-color);
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(37, 99, 235, 0.4);
}

.status-step.active .step-text {
  color: var(--primary-color);
  font-weight: 600;
}

.status-step.completed .step-dot {
  border-color: #10b981;
  background: #10b981;
}

.status-step.completed .step-text {
  color: var(--text-color);
}

.status-current-detail {
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(15, 23, 42, 0.03);
  padding: 8px 12px;
  border-radius: 8px;
  margin-top: 6px;
  word-break: break-all;
  line-height: 1.5;
}

/* Expanded fullscreen view */
.expanded-view {
  display: flex;
  height: calc(100vh - 120px);
  gap: 24px;
}

.expanded-left {
  width: min(32vw, 340px);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  padding-right: 20px;
}

.expanded-left h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
  margin: 0 0 12px;
  flex-shrink: 0;
}

.expanded-landmark-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 4px;
}

.expanded-landmark-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  align-items: center;
  transition: border-color 0.2s;
}

.expanded-landmark-item:hover {
  border-color: var(--primary-color);
}

.expanded-thumb {
  width: 96px;
  height: 62px;
  flex-shrink: 0;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
}

.expanded-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.expanded-thumb.placeholder {
  color: var(--text-secondary);
}

.expanded-lm-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.expanded-lm-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
  line-height: 1.4;
}

.expanded-lm-bangumi {
  font-size: 12px;
  color: var(--text-secondary);
}

.expanded-right {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  padding-right: 8px;
}

.expanded-right .lib-ai-content {
  font-size: 14px;
  line-height: 1.8;
}

.lib-ai-error {
  margin: 10px 0;
}

.lib-ai-error :deep(.el-alert) {
  border-radius: 10px;
}

.history-failed-warn {
  font-size: 12px;
  color: #d97706;
  background: rgba(245, 158, 11, 0.1);
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
}

.plan-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
  padding: 10px 12px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 10px;
  background: var(--primary-soft);
  color: var(--primary-color);
  font-size: 13px;
}

.plan-progress span {
  flex: 1;
  min-width: 0;
}

.plan-progress button {
  flex-shrink: 0;
}

.plan-no-library {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.65);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.plan-no-library button {
  color: var(--primary-color);
}

@media (max-width: 820px) {
  .lib-empty {
    overflow-y: auto;
    min-height: 200px;
    padding: 20px 0;
  }
  .expanded-view {
    flex-direction: column;
    height: auto;
  }
  .expanded-left {
    width: 100%;
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid var(--border-color);
    padding: 0 0 15px;
  }
  .expanded-right {
    overflow: visible;
    padding: 0;
  }
  .expanded-thumb {
    width: 72px;
    height: 48px;
  }
}
</style>
