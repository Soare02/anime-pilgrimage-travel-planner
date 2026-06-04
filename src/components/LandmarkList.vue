<template>
  <div class="landmark-list">
    <div class="list-header">
      <h3>地标列表</h3>
      <el-tag v-if="points.length > 0" size="small" effect="dark">
        {{ checkedCount }}/{{ points.length }} 已选
      </el-tag>
    </div>

    <div v-if="points.length > 0" class="list-toolbar">
      <el-checkbox
        :model-value="allChecked"
        :indeterminate="someChecked"
        @change="handleCheckAll"
      >
        全选
      </el-checkbox>
      <div class="toolbar-actions">
        <el-button text size="small" @click="store.invertCheck()">反选</el-button>
        <el-button text size="small" @click="store.uncheckAll()">清空</el-button>
      </div>
    </div>

    <div v-if="points.length === 0 && !loading" class="empty-state">
      <el-empty description="请先搜索动漫作品" :image-size="60" />
    </div>

    <div v-else class="list-content scrollbar-wrapper">
      <div
        v-for="(point, index) in points"
        :key="point.id"
        class="landmark-item"
        :class="{
          active: selectedPointId === point.id,
          'has-day': point.day !== null,
          unchecked: !point.checked
        }"
      >
        <el-checkbox
          :model-value="point.checked"
          @change="store.toggleCheck(point.id)"
          @click.stop
        />
        <div
          class="landmark-body"
          @click="handleClick(point)"
        >
          <div class="landmark-index" :class="point.day ? `day-${point.day}` : ''">
            {{ point.day || index + 1 }}
          </div>
          <div class="landmark-thumb" v-if="point.image">
            <img :src="getThumbUrl(point.image)" :alt="point.name" loading="lazy" />
          </div>
          <div class="landmark-info">
            <div class="landmark-name">{{ point.name }}</div>
            <div class="landmark-meta">
              <span v-if="point.ep">EP{{ point.ep }}</span>
              <span v-if="point.s">{{ formatTime(point.s) }}</span>
              <span v-if="point.day" class="day-badge">第{{ point.day }}天</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'

const store = useAppStore()
const { points, selectedPointId, loading, checkedCount, allChecked, someChecked } = storeToRefs(store)

function handleCheckAll(val) {
  if (val) {
    store.checkAll()
  } else {
    store.uncheckAll()
  }
}

function handleClick(point) {
  store.selectPoint(point.id)
}

function getThumbUrl(imageUrl) {
  if (!imageUrl) return ''
  if (imageUrl.includes('?')) return imageUrl
  return imageUrl + '?plan=h160'
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
.landmark-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-bottom: 1px solid var(--border-color);
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-color);
}

.list-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
}

.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--card-bg);
}

.toolbar-actions {
  display: flex;
  gap: 4px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.list-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.landmark-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  transition: background-color 0.2s, opacity 0.2s;
  margin-bottom: 4px;
}

.landmark-item:hover {
  background-color: rgba(64, 158, 255, 0.1);
}

.landmark-item.active {
  background-color: rgba(64, 158, 255, 0.2);
  border: 1px solid rgba(64, 158, 255, 0.3);
}

.landmark-item.unchecked {
  opacity: 0.45;
}

.landmark-item.unchecked:hover {
  opacity: 0.7;
}

.landmark-body {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.landmark-index {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background-color: var(--primary-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
}

.landmark-thumb {
  flex-shrink: 0;
  width: 56px;
  height: 40px;
  border-radius: 4px;
  overflow: hidden;
}

.landmark-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.landmark-info {
  flex: 1;
  min-width: 0;
}

.landmark-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.landmark-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-secondary);
}

.day-badge {
  color: var(--primary-color);
  font-weight: 500;
}
</style>
