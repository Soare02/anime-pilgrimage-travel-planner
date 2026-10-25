<template>
  <section class="plan-result" :class="{ 'is-draft': !isComplete }" aria-label="逐日巡礼行程">
    <div class="plan-state" role="status">
      <strong>{{ isComplete ? '行程已生成' : '规划未通过，以下为草案' }}</strong>
      <span>{{ requestedDays }} 天 · {{ landmarks.length }} 个地点</span>
    </div>

    <div v-if="issues.length" class="plan-issues" role="alert">
      <strong>需要留意的问题</strong>
      <ul>
        <li v-for="(issue, index) in issues" :key="`${issue.code || 'issue'}-${index}`">
          {{ issue.message || issue.code || '行程校验未通过' }}
        </li>
      </ul>
    </div>

    <div class="plan-days">
      <section v-for="day in dayRows" :key="day.day" class="plan-day">
        <div class="plan-day-header">
          <strong>
            <span class="plan-day-dot" :style="{ background: dayColor(day.day) }"></span>
            第 {{ day.day }} 天
          </strong>
          <span>直线距离 {{ formatDistance(day.straight_line_distance_m) }}</span>
        </div>
        <p v-if="!day.points.length" class="plan-empty-day">没有安排选中的点位</p>
        <ol v-else class="plan-stops">
          <li v-for="(point, index) in day.points" :key="String(point.id)" class="plan-stop">
            <button
              class="plan-stop-button"
              :aria-label="`在地图上查看第 ${day.day} 天第 ${index + 1} 站：${point.name || point.id}`"
              @click="emit('select-point', point)"
            >
              <span class="plan-stop-number" :style="{ background: dayColor(day.day) }">{{ index + 1 }}</span>
              <span class="plan-stop-thumb" :class="{ placeholder: !getImageUrl(point.image) || brokenImages.has(String(point.id)) }">
                <img
                  v-if="getImageUrl(point.image) && !brokenImages.has(String(point.id))"
                  :src="getImageUrl(point.image, 'h160')"
                  :alt="`${point.name || point.id} 场景截图`"
                  referrerpolicy="no-referrer"
                  loading="lazy"
                  @error="brokenImages.add(String(point.id))"
                />
                <span v-else aria-hidden="true">◫</span>
              </span>
              <span class="plan-stop-main">
                <strong>{{ point.name || point.cn || point.id }}</strong>
                <span class="plan-stop-meta" v-if="point.bangumiName || point.ep || point.s !== undefined">
                  {{ point.bangumiName || '取景地' }}<template v-if="point.ep"> · EP{{ point.ep }}</template><template v-if="point.s !== undefined && point.s !== null"> · {{ formatSeconds(point.s) }}</template>
                </span>
              </span>
            </button>
            <div v-if="noteFor(point.id) || warningsFor(point.id).length" class="plan-note">
              <p v-if="noteFor(point.id)?.scene_description">{{ noteFor(point.id).scene_description }}</p>
              <p v-if="noteFor(point.id)?.photo_advice"><strong>拍照建议：</strong>{{ noteFor(point.id).photo_advice }}</p>
              <p v-if="noteFor(point.id)?.cautions"><strong>注意：</strong>{{ noteFor(point.id).cautions }}</p>
              <div v-if="noteFor(point.id)?.inferred || noteFor(point.id)?.insufficient_data" class="plan-note-flags">
                <span v-if="noteFor(point.id)?.inferred">含推测内容</span>
                <span v-if="noteFor(point.id)?.insufficient_data">资料不足</span>
              </div>
              <div v-if="sourcesFor(point.id).length" class="plan-note-sources">
                参考资料：<template v-for="(source, sourceIndex) in sourcesFor(point.id)" :key="source.source_id">
                  <a v-if="safeUrl(source.url)" :href="safeUrl(source.url)" target="_blank" rel="noopener noreferrer">{{ source.title || `来源 ${sourceIndex + 1}` }}</a><span v-else>{{ source.title || `来源 ${sourceIndex + 1}` }}</span><span v-if="sourceIndex < sourcesFor(point.id).length - 1">、</span>
                </template>
              </div>
              <p v-for="(warning, warningIndex) in warningsFor(point.id)" :key="`${warning.code || 'warning'}-${warningIndex}`" class="plan-point-warning">
                提示：{{ warning.message || warning.code }}
              </p>
            </div>
          </li>
        </ol>
      </section>
    </div>

    <section v-if="unassigned.length" class="plan-unassigned">
      <strong>未安排的选中地点</strong>
      <div class="plan-unassigned-list">
        <button v-for="point in unassigned" :key="String(point.id)" @click="emit('select-point', point)">
          {{ point.name || point.cn || point.id }}
        </button>
      </div>
    </section>

    <section v-if="!isComplete" class="plan-snapshot">
      <strong>本次选择的全部地点</strong>
      <ul>
        <li v-for="point in landmarks" :key="String(point.id)">
          {{ point.name || point.cn || point.id }}
          <span>{{ assignedIds.has(String(point.id)) ? '已安排' : '未安排' }}</span>
        </li>
      </ul>
    </section>

    <details v-if="validSources.length" class="plan-source-list">
      <summary>参考资料（{{ validSources.length }}）</summary>
      <ul>
        <li v-for="source in validSources" :key="source.source_id">
          <a v-if="safeUrl(source.url)" :href="safeUrl(source.url)" target="_blank" rel="noopener noreferrer">{{ source.title || source.url }}</a>
          <span v-else>{{ source.title || '来源链接不可用' }}</span>
          <span class="source-meta">{{ reviewLabel(source.review_status) }}<template v-if="source.retrieved_at"> · {{ source.retrieved_at }}</template></span>
        </li>
      </ul>
    </details>

    <div v-if="warnings.length" class="plan-warnings">
      <strong>提示</strong>
      <ul>
        <li v-for="(warning, index) in warnings" :key="`${warning.code || 'warning'}-${index}`">
          {{ warning.message || warning.code }}
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { getImageUrl } from '../utils/imageUrl'

const props = defineProps({
  plan: { type: Object, required: true },
  landmarks: { type: Array, default: () => [] }
})
const emit = defineEmits(['select-point'])
const brokenImages = reactive(new Set())
const dayColors = ['#2563eb', '#0ea5e9', '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#14b8a6']

const isComplete = computed(() => props.plan.status === 'complete' && props.plan.validation?.passed === true)
const pointsById = computed(() => new Map(props.landmarks.map(point => [String(point.id), point])))
const requestedDays = computed(() => Number(props.plan.request_snapshot?.days) || props.plan.days?.length || 0)
const dayRows = computed(() => (props.plan.days || []).map(day => ({
  ...day,
  points: (day.point_ids || []).map(id => pointsById.value.get(String(id))).filter(Boolean)
})))
const assignedIds = computed(() => new Set(dayRows.value.flatMap(day => day.points.map(point => String(point.id)))))
const unassigned = computed(() => props.landmarks.filter(point => !assignedIds.value.has(String(point.id))))
const notesById = computed(() => new Map((props.plan.point_notes || []).map(note => [String(note.point_id), note])))
const sourcesById = computed(() => new Map((props.plan.sources || []).map(source => [String(source.source_id), source])))
const validSources = computed(() => (props.plan.sources || []).filter(source => source && source.source_id))
const issues = computed(() => props.plan.validation?.errors || [])
const warnings = computed(() => props.plan.validation?.warnings || [])

function dayColor(day) { return dayColors[(Math.max(1, Number(day)) - 1) % dayColors.length] }
function noteFor(id) { return notesById.value.get(String(id)) }
function sourcesFor(id) {
  return (noteFor(id)?.source_ids || []).map(sourceId => sourcesById.value.get(String(sourceId))).filter(Boolean)
}
function warningsFor(id) {
  return warnings.value.filter(warning =>
    (warning.point_ids || (warning.point_id == null ? [] : [warning.point_id])).some(pointId => String(pointId) === String(id))
  )
}
function safeUrl(url) { return /^https?:\/\/[^\s]+$/i.test(url || '') ? url : '' }
function reviewLabel(status) {
  return { approved: '已审核', unreviewed: '未审核', missing: '来源缺失' }[status] || '审核状态未知'
}
function formatDistance(meters) {
  const value = Number(meters)
  if (!Number.isFinite(value) || value < 0) return '未知'
  return value < 1000 ? `${Math.round(value)} 米` : `${(value / 1000).toFixed(1)} 公里`
}
function formatSeconds(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value < 0) return ''
  const minutes = Math.floor(value / 60)
  return `${minutes}:${String(Math.floor(value % 60)).padStart(2, '0')}`
}
</script>

<style scoped>
.plan-result {
  display: grid;
  gap: 14px;
  margin: 12px 0 16px;
  font-size: 13px;
  color: var(--text-color);
}

.plan-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 12px;
  background: var(--primary-soft);
}

.plan-state strong {
  font-size: 13px;
  color: var(--primary-color);
}

.plan-state span {
  flex-shrink: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.is-draft .plan-state {
  border-color: rgba(245, 158, 11, 0.3);
  background: rgba(245, 158, 11, 0.08);
}

.is-draft .plan-state strong {
  color: #d97706;
}

.plan-issues,
.plan-warnings {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
  line-height: 1.6;
  font-size: 12px;
}

.plan-warnings {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
}

.plan-issues ul,
.plan-warnings ul {
  padding-left: 16px;
  margin: 6px 0 0;
}

.plan-days {
  display: grid;
  gap: 12px;
}

.plan-day {
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  overflow: hidden;
}

.plan-day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(15, 23, 42, 0.03);
  border-bottom: 1px solid var(--border-color);
}

.plan-day-header strong {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.plan-day-header > span {
  text-align: right;
  color: var(--text-secondary);
  font-size: 12px;
}

.plan-day-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.plan-empty-day {
  padding: 14px;
  margin: 0;
  color: var(--text-secondary);
}

.plan-stops {
  list-style: none;
  padding: 0;
  margin: 0;
}

.plan-stop + .plan-stop {
  border-top: 1px solid var(--border-color);
}

.plan-stop-button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;
}

.plan-stop-button:hover,
.plan-unassigned-list button:hover {
  background: var(--primary-soft);
}

.plan-stop-number {
  display: grid;
  place-items: center;
  flex: 0 0 22px;
  height: 22px;
  border-radius: 50%;
  color: #ffffff;
  font-weight: 600;
  font-size: 11px;
}

.plan-stop-thumb {
  display: grid;
  place-items: center;
  flex: 0 0 42px;
  height: 32px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.05);
}

.plan-stop-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.plan-stop-thumb.placeholder {
  color: var(--text-muted);
  font-size: 14px;
}

.plan-stop-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.plan-stop-main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-color);
}

.plan-stop-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
}

.plan-note {
  padding: 0 12px 12px 44px;
  line-height: 1.6;
  font-size: 12px;
  color: var(--text-secondary);
}

.plan-note p {
  margin: 4px 0;
}

.plan-note strong {
  color: var(--text-color);
}

.plan-note-flags {
  display: flex;
  gap: 6px;
  margin: 6px 0;
}

.plan-note-flags span {
  padding: 2px 6px;
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
  border-radius: 4px;
  font-size: 11px;
}

.plan-note-sources a,
.plan-source-list a {
  color: var(--primary-color);
  text-decoration: none;
  overflow-wrap: anywhere;
}

.plan-note-sources a:hover,
.plan-source-list a:hover {
  text-decoration: underline;
}

.plan-point-warning {
  color: #d97706;
}

.plan-unassigned,
.plan-snapshot {
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 10px;
  background: rgba(254, 252, 232, 0.7);
}

.plan-unassigned-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.plan-unassigned-list button {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.85);
  color: var(--text-color);
  font-size: 12px;
  cursor: pointer;
}

.plan-snapshot ul,
.plan-source-list ul {
  margin: 8px 0 0;
  padding-left: 18px;
}

.plan-snapshot li {
  margin: 4px 0;
}

.plan-snapshot li span {
  margin-left: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.plan-source-list {
  border-top: 1px solid var(--border-color);
  padding-top: 10px;
  font-size: 12px;
}

.plan-source-list summary {
  cursor: pointer;
  font-weight: 600;
}

.plan-source-list li {
  margin: 6px 0;
  overflow-wrap: anywhere;
}

.source-meta {
  margin-left: 6px;
  color: var(--text-secondary);
}
</style>
