<template>
  <div class="landmark-dock" v-if="points.length > 0">
    <div class="dock-header">
      <span class="dock-title">地标列表</span>
      <span class="dock-count">{{ points.length }} 个地点</span>
    </div>
    <div class="dock-scroll-wrapper">
      <div class="dock-fade dock-fade-left" :class="{ visible: canScrollLeft }"></div>
      <div class="dock-fade dock-fade-right" :class="{ visible: canScrollRight }"></div>
      <div ref="scrollRef" class="dock-scroll" @wheel.prevent="onWheel" @scroll="updateFade">
        <div
          v-for="(point, index) in points"
          :key="point.id"
          class="dock-item"
          :class="{ active: selectedPointId === point.id }"
          @click="handleClick(point)"
        >
          <div class="dock-thumb" v-if="point.image">
            <img :src="getThumbUrl(point.image)" :alt="point.name" loading="lazy" />
          </div>
          <div class="dock-thumb placeholder" v-else>
            <span>{{ index + 1 }}</span>
          </div>
          <div class="dock-info">
            <div class="dock-name">{{ point.name }}</div>
            <div class="dock-meta">
              <span v-if="point.ep">EP{{ point.ep }}</span>
              <span v-if="point.s">{{ formatTime(point.s) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'

const store = useAppStore()
const { points, selectedPointId } = storeToRefs(store)

const scrollRef = ref(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
const scrollWrapperRef = ref(null)

const SCROLL_MULTIPLIER = 2.5
const SCROLL_DURATION = 130
const BOUNCE_DISTANCE = 12
const BOUNCE_DURATION = 150
let scrolling = false

function onWheel(e) {
  if (!scrollRef.value) return
  const el = scrollRef.value
  const raw = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX
  const delta = raw * SCROLL_MULTIPLIER

  const maxScroll = el.scrollWidth - el.clientWidth
  const atStart = el.scrollLeft <= 0 && delta < 0
  const atEnd = el.scrollLeft >= maxScroll - 1 && delta > 0

  if (atStart || atEnd) {
    bounce(el, delta > 0 ? 1 : -1)
    return
  }

  smoothScroll(el, delta)
}

function smoothScroll(el, distance) {
  if (scrolling) return
  scrolling = true
  const start = el.scrollLeft
  const startTime = performance.now()

  function tick(now) {
    const elapsed = now - startTime
    const progress = Math.min(elapsed / SCROLL_DURATION, 1)
    const eased = 1 - Math.pow(1 - progress, 2)
    el.scrollLeft = start + distance * eased
    updateFade()
    if (progress < 1) {
      requestAnimationFrame(tick)
    } else {
      scrolling = false
    }
  }
  requestAnimationFrame(tick)
}

function bounce(el, direction) {
  if (scrolling) return
  scrolling = true
  const start = el.scrollLeft
  const startTime = performance.now()

  function tick(now) {
    const elapsed = now - startTime
    const progress = Math.min(elapsed / BOUNCE_DURATION, 1)
    const eased = Math.sin(progress * Math.PI)
    el.scrollLeft = start + BOUNCE_DISTANCE * direction * eased
    if (progress < 1) {
      requestAnimationFrame(tick)
    } else {
      scrolling = false
    }
  }
  requestAnimationFrame(tick)
}

function updateFade() {
  if (!scrollRef.value) return
  const el = scrollRef.value
  canScrollLeft.value = el.scrollLeft > 2
  canScrollRight.value = el.scrollLeft < el.scrollWidth - el.clientWidth - 2
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
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

watch(points, () => {
  nextTick(updateFade)
})

onMounted(() => {
  nextTick(updateFade)
})
</script>

<style scoped>
.landmark-dock {
  position: absolute;
  bottom: 16px;
  left: 400px;
  right: 20px;
  z-index: 900;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  max-height: 260px;
  overflow: hidden;
}

.dock-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
}

.dock-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.dock-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.dock-scroll-wrapper {
  position: relative;
  overflow: hidden;
}

.dock-fade {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 32px;
  z-index: 2;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.dock-fade.visible {
  opacity: 1;
}

.dock-fade-left {
  left: 0;
  background: linear-gradient(to right, rgba(255, 255, 255, 0.72), transparent);
}

.dock-fade-right {
  right: 0;
  background: linear-gradient(to left, rgba(255, 255, 255, 0.72), transparent);
}

.dock-scroll {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.dock-scroll::-webkit-scrollbar {
  height: 4px;
}

.dock-scroll::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 2px;
}

.dock-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.dock-item {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.45);
  border: 1px solid rgba(208, 215, 222, 0.4);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 180px;
  max-width: 220px;
}

.dock-item:hover {
  background: rgba(9, 105, 218, 0.08);
  border-color: rgba(9, 105, 218, 0.25);
  transform: translateY(-2px);
}

.dock-item.active {
  background: rgba(9, 105, 218, 0.15);
  border-color: rgba(9, 105, 218, 0.45);
  box-shadow: 0 4px 12px rgba(9, 105, 218, 0.15);
}

.dock-item.active .dock-name {
  color: var(--primary-color);
  font-weight: 600;
}

.dock-thumb {
  flex-shrink: 0;
  width: 48px;
  height: 34px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.05);
}

.dock-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-secondary);
}

.dock-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.dock-info {
  flex: 1;
  min-width: 0;
}

.dock-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.3;
}

.dock-meta {
  display: flex;
  gap: 6px;
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 2px;
}
</style>
