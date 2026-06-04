<template>
  <div class="itinerary-panel">
    <div class="panel-header">
      <h3>路线规划</h3>
    </div>

    <div class="controls">
      <div class="days-control">
        <span class="control-label">行程天数</span>
        <el-input-number
          v-model="days"
          :min="1"
          :max="7"
          size="default"
          :disabled="checkedCount === 0"
        />
      </div>
      <el-button
        type="primary"
        @click="handleGenerate"
        :loading="loading"
        :disabled="checkedCount === 0"
        style="width: 100%"
      >
        生成路线
      </el-button>
      <div v-if="points.length > 0" class="select-hint">
        <span v-if="checkedCount === 0" class="hint-warn">请在底部 Dock 中选择地标</span>
        <span v-else class="hint-info">将为选中的 {{ checkedCount }} 个地点规划路线</span>
      </div>
    </div>

    <div v-if="itinerary.length > 0" class="itinerary-content scrollbar-wrapper">
      <div v-for="day in itinerary" :key="day.day" class="day-section">
        <div class="day-header">
          <div class="day-title">
            <span class="day-badge" :class="`day-${day.day}`">第{{ day.day }}天</span>
            <span class="day-stats">{{ day.pointCount }} 个地点 · {{ day.distance }} km</span>
          </div>
        </div>
        <div class="day-points">
          <div
            v-for="(point, idx) in day.points"
            :key="point.id"
            class="day-point-item"
            @click="handlePointClick(point)"
          >
            <div class="point-number" :class="`day-${day.day}`">{{ idx + 1 }}</div>
            <div class="point-info">
              <div class="point-name">{{ point.name }}</div>
              <div class="point-meta">
                <span v-if="point.ep">EP{{ point.ep }}</span>
                <span v-if="point.s">{{ formatTime(point.s) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="checkedCount > 0 && !loading" class="empty-hint">
      <p>点击"生成路线"按钮为选中的 {{ checkedCount }} 个地点规划行程</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'

const store = useAppStore()
const { points, checkedCount, itinerary, loading } = storeToRefs(store)

const days = computed({
  get: () => store.days,
  set: (val) => { store.days = val }
})

async function handleGenerate() {
  await store.generateItinerary()
}

function handlePointClick(point) {
  store.selectPoint(point.id)
}

function formatTime(seconds) {
  if (!seconds) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.itinerary-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.panel-header {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
}

.panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
}

.controls {
  padding: 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-bottom: 1px solid var(--border-color);
}

.days-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.control-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.select-hint {
  text-align: center;
  font-size: 12px;
  line-height: 1.4;
}

.hint-warn {
  color: #E6A23C;
}

.hint-info {
  color: var(--text-secondary);
}

.itinerary-content {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.day-section {
  margin-bottom: 14px;
}

.day-header {
  padding: 8px 10px;
  background-color: var(--card-bg);
  border-radius: 6px;
  margin-bottom: 6px;
}

.day-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.day-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  background-color: var(--primary-color);
}

.day-stats {
  font-size: 12px;
  color: var(--text-secondary);
}

.day-points {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.day-point-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.day-point-item:hover {
  background-color: rgba(64, 158, 255, 0.08);
}

.point-number {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background-color: var(--primary-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: bold;
}

.point-info {
  flex: 1;
  min-width: 0;
}

.point-name {
  font-size: 13px;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.point-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 1px;
}

.empty-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.empty-hint p {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}
</style>
