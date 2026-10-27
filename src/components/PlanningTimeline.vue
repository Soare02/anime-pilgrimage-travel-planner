<template>
  <section class="planning-timeline" aria-label="AI 规划过程">
    <header class="timeline-header">
      <div class="timeline-title"><el-icon><List /></el-icon><strong>规划过程</strong></div>
      <button v-if="status === 'running'" type="button" class="timeline-cancel" @click="emit('cancel')">取消规划</button>
    </header>
    <p v-if="requestLabel" class="timeline-context">{{ requestLabel }}</p>
    <div class="timeline-current">
      <span role="status" aria-live="polite">{{ headline }}</span>
      <span v-if="startedAt" class="timeline-elapsed">{{ elapsedLabel }} {{ formatDuration(elapsed) }}</span>
    </div>
    <div class="timeline-stages">
      <article v-for="(group, index) in groups" :key="group.id" class="timeline-stage" :class="`is-${group.status}`">
        <span class="stage-marker" aria-hidden="true">
          <span v-if="group.status === 'pending' || group.status === 'skipped'">{{ index + 1 }}</span>
          <el-icon v-else :class="{ 'is-loading': group.status === 'running' }"><component :is="statusIcon(group.status)" /></el-icon>
        </span>
        <details v-if="group.details.length" :open="group.status === 'running'">
          <summary>
            <div class="stage-heading">
              <strong class="stage-title">{{ group.title }}</strong>
              <span class="stage-status">{{ statusLabel(group.status) }}</span>
              <span v-if="group.duration_ms" class="stage-duration">{{ formatDuration(group.duration_ms) }}</span>
              <el-icon class="stage-arrow"><ArrowDown /></el-icon>
            </div>
            <p class="stage-summary">{{ group.summary }}</p>
          </summary>
          <ol class="stage-details">
            <li v-for="detail in group.details" :key="detail.id" class="detail-item" :class="`is-${detail.status}`">
              <el-icon class="detail-icon" :class="{ 'is-loading': detail.status === 'running' }" aria-hidden="true"><component :is="statusIcon(detail.status)" /></el-icon>
              <div class="detail-body">
                <div class="detail-heading"><strong>{{ detail.title }}</strong><span>{{ statusLabel(detail.status) }}<template v-if="detail.duration_ms"> · {{ formatDuration(detail.duration_ms) }}</template></span></div>
                <p>{{ detail.summary }}</p>
              </div>
            </li>
          </ol>
        </details>
        <div v-else>
          <div class="stage-heading">
            <strong class="stage-title">{{ group.title }}</strong>
            <span class="stage-status">{{ statusLabel(group.status) }}</span>
            <span v-if="group.duration_ms" class="stage-duration">{{ formatDuration(group.duration_ms) }}</span>
          </div>
          <p class="stage-summary">{{ group.summary }}</p>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElIcon } from 'element-plus/es/components/icon/index.mjs'
import { ArrowDown, Check, Clock, Close, List, Loading, Minus, Warning } from '@element-plus/icons-vue'
import { groupPlanningSteps, planningHeadline } from '../utils/planningProgress'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  status: { type: String, default: 'running' },
  startedAt: { type: String, default: null },
  finishedAt: { type: String, default: null },
  requestSnapshot: { type: Object, default: null }
})
const emit = defineEmits(['cancel'])
const now = ref(Date.now())
let timer = null
const groups = computed(() => groupPlanningSteps(props.steps, props.status, now.value))
const headline = computed(() => planningHeadline(groups.value, props.status))
const requestLabel = computed(() => {
  const snapshot = props.requestSnapshot
  if (!snapshot?.landmarks?.length) return ''
  const works = new Set(snapshot.landmarks.map(point => point.bangumiName || point.bangumiOriginalName).filter(Boolean))
  return `${snapshot.landmarks.length} 处地点${works.size ? ` · ${works.size} 部作品` : ''} · ${snapshot.days || 1} 天`
})
const elapsed = computed(() => {
  const start = Date.parse(props.startedAt)
  const end = props.finishedAt ? Date.parse(props.finishedAt) : props.status === 'running' ? now.value : start
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : 0
})
const elapsedLabel = computed(() => props.status === 'running' ? '已运行' : '总用时')
function statusLabel(status) {
  return { pending: '等待开始', running: '执行中', completed: '已完成', warning: '有提示', failed: '未通过', cancelled: '已取消', skipped: '未执行' }[status] || ''
}
function statusIcon(status) {
  return { running: Loading, completed: Check, warning: Warning, failed: Close, cancelled: Close, skipped: Minus }[status] || Clock
}
function formatDuration(ms) {
  if (ms < 1000) return '不到 1 秒'
  const seconds = Math.floor(ms / 1000)
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
onMounted(() => {
  watch(() => props.status, status => {
    clearInterval(timer)
    timer = null
    now.value = Date.now()
    if (status === 'running') timer = setInterval(() => { now.value = Date.now() }, 1000)
  }, { immediate: true })
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.planning-timeline { margin: 12px 0; padding: 16px; border: 1px solid var(--border-color); border-radius: 14px; background: var(--surface-solid, #fff); color: var(--text-color); font-size: 13px; }
.timeline-header, .timeline-title { display: flex; align-items: center; gap: 7px; }
.timeline-header { justify-content: space-between; }
.timeline-title { color: var(--text-color); }
.timeline-title > .el-icon { color: var(--primary-color); font-size: 16px; }
.timeline-title strong { font-weight: 600; }
.timeline-cancel { border: 0; background: transparent; color: var(--primary-color); font: inherit; font-size: 12px; padding: 4px 0 4px 8px; cursor: pointer; }
.timeline-context { margin: 5px 0 10px; color: var(--text-secondary); font-size: 12px; }
.timeline-current { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 5px 10px; margin: 10px 0 16px; color: var(--primary-color); font-size: 12px; }
.timeline-elapsed { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.timeline-stage { position: relative; padding: 0 0 17px 33px; }
.timeline-stage:last-child { padding-bottom: 0; }
.timeline-stage::before { content: ''; position: absolute; top: 28px; bottom: 0; left: 10px; width: 1px; background: var(--border-color); }
.timeline-stage:last-child::before { display: none; }
.stage-marker { position: absolute; top: 2px; left: 0; display: grid; place-items: center; width: 22px; height: 22px; border: 1px solid var(--border-color); border-radius: 50%; background: var(--surface-solid, #fff); color: var(--text-secondary); font-size: 11px; }
.is-completed > .stage-marker { color: var(--el-color-success); }
.is-running > .stage-marker { color: var(--primary-color); border-color: var(--primary-color); background: var(--primary-soft); }
.is-warning > .stage-marker { color: var(--el-color-warning); }
.is-failed > .stage-marker { color: var(--el-color-danger); }
.stage-heading { display: flex; align-items: center; gap: 5px 7px; flex-wrap: wrap; min-height: 26px; }
.stage-title { flex: 1; min-width: 0; font-size: 13px; font-weight: 500; }
.stage-status, .stage-duration { color: var(--text-secondary); font-size: 11px; white-space: nowrap; }
.stage-duration { font-variant-numeric: tabular-nums; }
.is-running .stage-status { color: var(--primary-color); }
.is-failed .stage-status { color: var(--el-color-danger); }
.stage-summary { margin: 3px 0 0; color: var(--text-secondary); line-height: 1.65; font-size: 12px; overflow-wrap: anywhere; }
.is-running > details > summary .stage-summary { color: var(--text-color); }
details > summary { list-style: none; cursor: pointer; border-radius: 4px; }
details > summary::-webkit-details-marker { display: none; }
.stage-arrow { color: var(--text-secondary); font-size: 11px; flex: 0 0 11px; }
details[open] > summary .stage-arrow { transform: rotate(180deg); }
.stage-details { display: grid; gap: 11px; margin: 10px 0 0; padding: 11px; list-style: none; border-radius: 9px; background: var(--bg-color); }
.is-running > details > .stage-details { background: var(--primary-soft); }
.detail-item { display: flex; align-items: flex-start; gap: 7px; }
.detail-icon { margin-top: 4px; flex: 0 0 13px; font-size: 13px; color: var(--el-color-success); }
.detail-item.is-running .detail-icon { color: var(--primary-color); }
.detail-item.is-warning .detail-icon { color: var(--el-color-warning); }
.detail-item.is-failed .detail-icon { color: var(--el-color-danger); }
.detail-item.is-cancelled .detail-icon, .detail-item.is-skipped .detail-icon { color: var(--text-secondary); }
.detail-body { flex: 1; min-width: 0; }
.detail-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 7px; font-size: 12px; }
.detail-heading strong { font-weight: 500; overflow-wrap: anywhere; }
.detail-heading span { color: var(--text-secondary); font-size: 11px; }
.detail-body p { margin: 3px 0 0; color: var(--text-secondary); line-height: 1.6; font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 400px) { .planning-timeline { padding: 13px; } .timeline-stage { padding-left: 30px; } }
@media (prefers-reduced-motion: reduce) { .is-loading { animation: none !important; } }
</style>
