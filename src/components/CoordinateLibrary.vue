<template>
  <div class="coordinate-library">
    <header class="library-heading">
      <span class="eyebrow">{{
        activeTab === 'library'
          ? 'COLLECT MOMENTS, MAKE MEMORIES'
          : 'PAGES FROM YOUR JOURNEY'
      }}</span>
      <h1>
        {{ activeTab === 'library' ? '我的巡礼' : '旅途档案' }}<span>.</span>
      </h1>
      <p>
        {{
          activeTab === 'library'
            ? '把想去的地方，连成自己的故事。'
            : '每一次出发，都值得好好珍藏。'
        }}
      </p>
    </header>

    <!-- 坐标库 -->
    <template v-if="activeTab === 'library'">
      <div v-if="coordinateLibrary.length === 0" class="lib-empty">
        <div class="empty-illustration">
          <span></span><AppIcon name="bookmark" :size="38" /><span></span>
        </div>
        <span class="eyebrow">A BLANK PAGE, A NEW ADVENTURE</span>
        <h2>旅程，从一处心动开始</h2>
        <p>在地图或场景卡片上收藏喜欢的地标，<br />它们会在这里等你出发。</p>
        <button class="primary-button" @click="emit('explore')">
          去发现圣地 <AppIcon name="arrow" :size="16" />
        </button>
      </div>

      <template v-else>
        <div class="lib-body-scroll">
          <div class="lib-toolbar">
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
              <span class="selection-count"
                >已选 {{ librarySelected.length }} /
                {{ coordinateLibrary.length }}</span
              >
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

          <div class="lib-list">
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
                  loading="lazy"
                />
              </div>
              <div class="lib-thumb placeholder" v-else>
                <el-icon :size="14"><Star /></el-icon>
              </div>
              <button class="lib-info" @click="focusLandmark(entry)">
                <div class="lib-name">{{ entry.name }}</div>
                <div class="lib-source" v-if="entry.bangumiName">
                  {{ entry.bangumiName }}
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

          <div class="lib-controls">
            <div class="planner-heading">
              <AppIcon name="sparkles" :size="18" />
              <div>
                <strong>把下一站，交给 AI</strong
                ><small>根据所选地标，为你安排巡礼路线</small>
              </div>
            </div>
            <div class="lib-days-row">
              <span class="lib-label">这次，想旅行几天？</span>
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
              size="small"
              @click="handleGenerate"
              :loading="planning"
              :disabled="librarySelected.length === 0 || (loading && !planning)"
            >
              <AppIcon v-if="!planning" name="sparkles" :size="15" />{{
                planning ? '正在编排旅程…' : '生成我的巡礼路线'
              }}
            </el-button>
            <button
              class="planner-settings text-button"
              @click="store.settingsOpen = true"
            >
              {{ getSchemeLabel(store.aiConfig.scheme) }}
              <AppIcon name="settings" :size="12" />
            </button>
          </div>

          <div v-if="store.error && !planning" class="lib-ai-error">
            <el-alert
              :title="store.error"
              type="error"
              show-icon
              :closable="false"
            />
          </div>
          <div v-if="libraryAiResponse || planning" class="lib-ai-response">
            <div class="lib-ai-header">
              <span class="lib-ai-badge">AI 路线规划</span>
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
              v-if="planning && !parsedAiResponse.cleanMarkdown"
              class="ai-status-loader"
            >
              <div class="status-spinner-row">
                <el-icon class="is-loading" :size="20"><Loading /></el-icon>
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
                  <span class="step-text">动漫原作名场面还原匹配</span>
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
                  <span class="step-text">检查行程与整理手帖</span>
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
          <span></span><AppIcon name="clock" :size="38" /><span></span>
        </div>
        <span class="eyebrow">THE FIRST CHAPTER IS YOURS</span>
        <h2>你的故事，待续</h2>
        <p>
          生成的巡礼路线会自动收录在这里。<br />下一次出发，从翻开手帖开始。
        </p>
        <button class="primary-button" @click="store.activePanel = 'library'">
          规划第一段旅程 <AppIcon name="arrow" :size="16" />
        </button>
      </div>

      <template v-else>
        <div class="lib-toolbar">
          <span class="lib-history-count"
            >{{ routeHistory.length }} 条记录</span
          >
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
                <div style="display: flex; align-items: center; gap: 6px">
                  <span class="history-time">{{
                    formatTimestamp(record.timestamp)
                  }}</span>
                  <span :class="['scheme-badge', record.scheme || 'cloud']">
                    {{ getSchemeLabel(record.scheme) }}
                  </span>
                </div>
                <span class="history-meta"
                  >{{ record.days }}天 ·
                  {{ record.landmarks.length }}个地点</span
                >
              </div>
              <div class="history-actions">
                <el-button
                  text
                  size="small"
                  type="danger"
                  @click.stop="handleDelete(record.id)"
                  >删除</el-button
                >
                <el-icon
                  class="history-arrow"
                  :class="{ rotated: expandedId === record.id }"
                >
                  <ArrowDown />
                </el-icon>
              </div>
            </div>

            <div v-if="expandedId === record.id" class="history-body">
              <div
                v-if="expandedCache[record.id]?.loading"
                class="history-loading"
              >
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载地标信息...</span>
              </div>
              <template v-else-if="expandedCache[record.id]?.landmarkList">
                <div class="history-landmarks">
                  <div class="history-section-title">地标列表</div>
                  <div
                    v-for="(pt, idx) in expandedCache[record.id].landmarkList"
                    :key="pt.id"
                    class="history-landmark-item"
                    @click="handleHistoryLandmarkClick(pt)"
                  >
                    <span class="hl-index">{{ idx + 1 }}</span>
                    <div class="hl-info">
                      <span class="hl-name">{{
                        pt.cn || pt.name || pt.id
                      }}</span>
                      <span class="hl-meta" v-if="pt.ep || pt.s">
                        <template v-if="pt.ep">EP{{ pt.ep }}</template>
                        <template v-if="pt.s">
                          · {{ formatSeconds(pt.s) }}</template
                        >
                      </span>
                    </div>
                    <el-icon class="hl-go" @click.stop="showHistoryImage(pt)"
                      ><View
                    /></el-icon>
                  </div>
                </div>
              </template>

              <div
                v-if="expandedCache[record.id]?.failedCount"
                class="history-failed-warn"
              >
                注意：{{
                  expandedCache[record.id].failedCount
                }}
                个地标信息加载失败
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
          :src="historyImageUrl.replace('?plan=h160', '?plan=h360')"
          :alt="historyImageName"
          class="history-image"
        />
      </div>
      <div class="history-compare-row">
        <button class="history-compare-btn" @click="handleHistoryCompare">
          对比
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
                :src="
                  lm.image.includes('?') ? lm.image : lm.image + '?plan=h360'
                "
                :alt="lm.name"
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
import { fetchBangumiLite, fetchBangumiPointsDetail } from '../utils/api'

const store = useAppStore()
const {
  coordinateLibrary,
  librarySelected,
  libraryAiResponse,
  loading,
  planning,
  routeHistory,
  generatedLandmarks
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
          missedCount++ // API 返回了但未找到该 point（可能被移除）
        }
      })
    } catch {
      failedCount += pointIds.length // 整组 API 调用失败
    }
  }

  if (expandedCache[record.id]) {
    expandedCache[record.id].landmarkList = landmarkList
    expandedCache[record.id].loading = false
    expandedCache[record.id].failedCount = failedCount + missedCount
  }
}

function handleHistoryLandmarkClick(pt) {
  const exists = store.coordinateLibrary.some((e) => e.id === pt.id)
  if (exists) {
    ElMessage.info('该地标已在坐标库中')
    return
  }
  store.coordinateLibrary.push({
    id: pt.id,
    name: pt.cn || pt.name || pt.id,
    originalName: pt.name || '',
    image: pt.image || '',
    ep: pt.ep,
    s: pt.s,
    geo: pt.geo,
    origin: pt.origin || '',
    originURL: pt.originURL || '',
    bangumiId: pt.bangumiId || null,
    bangumiName: pt.bangumiName || '',
    bangumiOriginalName: pt.bangumiOriginalName || '',
    checked: true
  })
  ElMessage.success('已添加到坐标库')
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
  } catch {
    // 用户取消删除
  }
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
  if (!imageUrl) return ''
  if (imageUrl.includes('?')) return imageUrl
  return imageUrl + '?plan=h160'
}

function renderMarkdown(text) {
  if (!text) return ''

  // Filter out status lines
  const cleanText = text
    .split('\n')
    .filter((line) => !line.startsWith('__STATUS__:'))
    .join('\n')

  // 转义 HTML
  const escaped = cleanText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 先处理行内格式（加粗）
  let html = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // 按空行分割成块
  const blocks = html.split(/\n\n+/)
  const out = blocks.map((block) => {
    block = block.trim()
    if (!block) return ''

    // 标题：仅取首行为标题，剩余行作正文（避免同块内容被吞进标题标签）
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

    // 无序列表（所有行都以 - 开头）
    if (lines.every((l) => /^\- /.test(l))) {
      return (
        '<ul>' + lines.map((l) => `<li>${l.slice(2)}</li>`).join('') + '</ul>'
      )
    }

    // 有序列表（所有行都以数字.开头）
    if (lines.every((l) => /^\d+\.\s/.test(l))) {
      return (
        '<ol>' +
        lines.map((l) => `<li>${l.replace(/^\d+\.\s*/, '')}</li>`).join('') +
        '</ol>'
      )
    }

    // 普通段落（内部换行用 <br>）
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
  padding-top: 8px;
}

.lib-empty {
  display: flex;
  flex: 1;
  min-height: 260px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 26px 8px 48px;
  color: var(--text-secondary);
  text-align: center;
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
  gap: 5px;
}

.lib-list {
  padding: 5px 0;
}

.lib-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 5px;
  border-radius: 8px;
  border-bottom: 1px solid var(--border-color);
  transition:
    background 0.2s,
    opacity 0.2s;
}

.lib-item:hover {
  background-color: rgba(60, 97, 75, 0.08);
}

.lib-item.unchecked {
  opacity: 0.45;
}

.lib-thumb {
  flex-shrink: 0;
  width: 54px;
  height: 42px;
  border-radius: 7px;
  overflow: hidden;
  background: var(--primary-soft);
}

.lib-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
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
  font-size: 12px;
  font-weight: 550;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.5;
}

.lib-source {
  font-size: 9px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
}

.lib-remove-btn {
  flex-shrink: 0;
  opacity: 0.45;
  transition: opacity 0.2s;
  padding: 2px !important;
  height: 28px !important;
}

.lib-item:hover .lib-remove-btn {
  opacity: 0.7;
}

.lib-remove-btn:hover {
  opacity: 1 !important;
  color: #f56c6c !important;
}

.lib-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 16px 14px;
  border: 1px solid #dce4d0;
  border-radius: 13px;
  background: #edf1e4;
  margin: 20px 0 14px;
}

.lib-days-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}

.lib-label {
  font-size: 11px;
  color: #738365;
  flex-shrink: 0;
}

.lib-body-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-right: 3px;
  overscroll-behavior: contain;
}

.lib-body-scroll::-webkit-scrollbar {
  width: 6px;
}

.lib-body-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.lib-body-scroll::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.lib-body-scroll::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.25);
}

.lib-ai-response {
  padding: 20px 0 10px;
  border-top: 1px dashed #d2dcc5;
  margin-top: 18px;
}

.lib-ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.lib-ai-badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 9px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
  color: var(--primary-color);
  background: var(--primary-soft);
}

.lib-copy-btn {
  margin-left: auto;
  color: var(--text-secondary) !important;
  transition: color 0.2s;
}

.lib-copy-btn:hover {
  color: #3c614b !important;
}

.lib-ai-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-color);
}

.lib-ai-content :deep(h2) {
  font-size: 16px;
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

/* Tabs */
.lib-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 20%;
  width: 60%;
  height: 2px;
  background: var(--primary-color);
  border-radius: 1px;
}

/* History */
.lib-history-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.history-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  padding: 12px 3px 12px 0;
}

.history-item {
  border: 1px solid var(--border-color);
  border-radius: 11px;
  background: var(--surface-color);
  overflow: hidden;
  margin-bottom: 12px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 12px;
  gap: 8px;
  cursor: pointer;
}

.history-header:hover {
  background-color: rgba(60, 97, 75, 0.06);
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-time {
  font-size: 12px;
  color: var(--text-color);
  font-weight: 500;
}

.history-meta {
  font-size: 11px;
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
  padding: 10px 12px;
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
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color);
}

.history-section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.history-landmarks {
  margin-bottom: 12px;
}

.history-landmark-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.history-landmark-item:hover {
  background-color: rgba(60, 97, 75, 0.1);
}

.hl-index {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: bold;
}

.hl-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.hl-name {
  font-size: 12px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hl-meta {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 1px;
}

.hl-go {
  font-size: 14px;
  color: var(--text-secondary);
  opacity: 0;
  transition: opacity 0.15s;
}

.history-landmark-item:hover .hl-go {
  opacity: 0.7;
}

.history-ai-response {
  margin-top: 4px;
}

.history-image-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
}

.history-compare-row {
  display: flex;
  justify-content: center;
  padding: 8px 0 2px;
}

.history-compare-btn {
  height: 16px;
  line-height: 16px;
  padding: 0 14px;
  border: 1px solid rgba(60, 97, 75, 0.4);
  background: rgba(60, 97, 75, 0.15);
  color: var(--primary-color);
  font-size: 11px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.history-compare-btn:hover {
  background: var(--primary-color);
  color: white;
}

.history-image {
  max-width: 100%;
  max-height: 60vh;
  border-radius: 6px;
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

:deep(.el-dialog) {
  background: var(--sidebar-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

:deep(.el-dialog__title) {
  color: var(--text-color);
  font-size: 15px;
}

:deep(.el-dialog__headerbtn .el-dialog__close) {
  color: var(--text-secondary);
}

:deep(.el-dialog__body) {
  padding: 12px 20px 20px;
}

.scheme-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 500;
  line-height: 1.2;
}

.scheme-badge.cloud {
  background-color: rgba(60, 97, 75, 0.08);
  color: #3c614b;
  border: 1px solid rgba(60, 97, 75, 0.2);
}

.scheme-badge.local {
  background-color: rgba(230, 162, 60, 0.08);
  color: #b06000;
  border: 1px solid rgba(230, 162, 60, 0.2);
}

.scheme-badge.agent {
  background-color: rgba(103, 194, 58, 0.08);
  color: #1a7f37;
  border: 1px solid rgba(103, 194, 58, 0.2);
}

/* AI Stream Planning progress status loader styling */
.ai-status-loader {
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: rgba(60, 97, 75, 0.04);
  border-radius: 12px;
  border: 1px dashed rgba(60, 97, 75, 0.25);
  margin: 12px 0;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.01);
}

.status-spinner-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.status-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.status-steps {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
  padding-left: 20px;
  margin-bottom: 16px;
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
  background: var(--sidebar-bg);
  border: 2px solid var(--border-color);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.step-text {
  font-size: 12px;
  color: var(--text-secondary);
  transition: all 0.3s ease;
}

/* Active step styles */
.status-step.active .step-dot {
  border-color: var(--primary-color);
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(60, 97, 75, 0.5);
  transform: scale(1.1);
  animation: pulse-border 2s infinite;
}

.status-step.active .step-text {
  color: var(--primary-color);
  font-weight: 600;
}

/* Completed step styles */
.status-step.completed .step-dot {
  border-color: #67c23a;
  background: #67c23a;
  box-shadow: none;
}

.status-step.completed .step-text {
  color: #67c23a;
}

.status-current-detail {
  font-size: 11px;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.02);
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  font-style: italic;
  margin-top: 8px;
  word-break: break-all;
  line-height: 1.4;
}

@keyframes pulse-border {
  0% {
    box-shadow: 0 0 0 0 rgba(60, 97, 75, 0.4);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(60, 97, 75, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(60, 97, 75, 0);
  }
}

/* Expand button group */
.lib-ai-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.lib-expand-btn {
  color: var(--text-secondary) !important;
  transition: color 0.2s;
}

.lib-expand-btn:hover {
  color: var(--primary-color) !important;
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

.expanded-landmark-list::-webkit-scrollbar {
  width: 6px;
}

.expanded-landmark-list::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.expanded-landmark-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--card-bg);
  align-items: center;
  transition: border-color 0.2s;
}

.expanded-landmark-item:hover {
  border-color: var(--primary-color);
}

.expanded-thumb {
  width: 100px;
  height: 64px;
  flex-shrink: 0;
  border-radius: 6px;
  overflow: hidden;
  background: var(--sidebar-bg);
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
  line-height: 1.3;
}

.expanded-lm-bangumi {
  font-size: 11px;
  color: var(--text-secondary);
}

.expanded-right {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  padding-right: 8px;
}

.expanded-right::-webkit-scrollbar {
  width: 6px;
}

.expanded-right::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.expanded-right .lib-ai-content {
  font-size: 14px;
  line-height: 1.8;
}

:deep(.el-dialog.is-fullscreen) {
  background: var(--sidebar-bg);
}

.lib-ai-error {
  margin-top: 8px;
}

.lib-ai-error :deep(.el-alert__content) {
  font-size: 12px;
}

.history-failed-warn {
  font-size: 11px;
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.08);
  padding: 6px 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}

.library-heading {
  padding: 2px 0 25px;
  flex-shrink: 0;
}
.library-heading .eyebrow {
  font-size: 8px;
  letter-spacing: 1.3px;
}
.library-heading h1 {
  font-size: 32px;
  font-weight: 600;
  letter-spacing: 2px;
  line-height: 1.5;
  margin: 20px 0 8px;
}
.library-heading h1 > span {
  color: var(--accent-color);
  margin-left: 4px;
}
.library-heading p {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.empty-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  width: 134px;
  height: 134px;
  background: #e9eee0;
  border: 1px dashed #cad6be;
  border-radius: 50%;
  color: #7d916b;
  margin-bottom: 28px;
  transform: rotate(-8deg);
}
.empty-illustration span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #bdc8a8;
}
.lib-empty .eyebrow {
  font-size: 7px;
  letter-spacing: 1.3px;
}
.lib-empty h2 {
  font-size: 17px;
  font-weight: 550;
  color: var(--text-color);
  margin: 13px 0;
}
.lib-empty p {
  font-size: 11px;
  line-height: 2;
}
.lib-empty .primary-button {
  margin-top: 25px;
}
.selection-count {
  font-size: 9px;
  color: #8d987f;
}
.lib-toolbar :deep(.el-checkbox__label) {
  font-size: 11px;
  color: var(--text-secondary);
}
.lib-toolbar :deep(.el-button) {
  font-size: 10px;
  padding: 4px 5px;
}
.planner-heading {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  color: var(--primary-color);
}
.planner-heading strong {
  font-size: 12px;
  font-weight: 600;
  display: block;
}
.planner-heading small {
  font-size: 9px;
  margin-top: 7px;
  display: block;
  color: #889779;
}
.lib-controls :deep(.el-input-number) {
  width: 104px;
}
.lib-controls > .el-button {
  min-height: 40px;
  width: 100%;
  font-size: 11px;
}
.lib-controls > .el-button :deep(span) {
  gap: 7px;
}
.planner-settings {
  font-size: 9px;
  margin-top: -6px;
  padding: 2px 0;
  color: #7e8f70;
}
.lib-ai-error {
  margin: 10px 0;
}
.lib-ai-error :deep(.el-alert) {
  padding: 10px;
}
.lib-remove-btn:focus-visible {
  opacity: 1;
}
.history-header:focus-visible {
  outline-offset: -3px;
}
.lib-ai-content {
  overflow-wrap: anywhere;
}
@media (max-width: 820px) {
  .library-heading {
    padding-bottom: 22px;
  }
  .library-heading h1 {
    margin-top: 14px;
  }
  .lib-empty {
    overflow-y: auto;
    min-height: 200px;
    padding: 15px 0 30px;
    justify-content: flex-start;
  }
  .empty-illustration {
    width: 110px;
    height: 110px;
    flex-shrink: 0;
    margin-bottom: 23px;
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
    width: 70px;
    height: 48px;
  }
}
</style>
