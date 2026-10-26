<template>
  <section
    v-if="displayPoints.length"
    class="landmark-dock"
    aria-label="场景地标列表"
  >
    <header class="dock-header">
      <div class="dock-title">
        <AppIcon name="camera" :size="16" />
        <h2>
          {{ store.activePanel === 'history' ? '档案地标' : store.activePanel === 'library' ? '收藏地标' : '场景地标' }}
        </h2>
        <span class="dock-count">{{ displayPoints.length }}</span>
      </div>
      <div class="dock-navigation">
        <button
          class="icon-button"
          :disabled="!canScrollLeft"
          aria-label="向前浏览地标"
          @click="scrollCards(-1)"
        >
          <AppIcon name="back" :size="15" />
        </button>
        <button
          class="icon-button"
          :disabled="!canScrollRight"
          aria-label="向后浏览地标"
          @click="scrollCards(1)"
        >
          <AppIcon name="arrow" :size="15" />
        </button>
      </div>
    </header>

    <div
      ref="scrollRef"
      class="dock-scroll"
      @wheel="onWheel"
      @scroll.passive="updateScroll"
    >
      <article
        v-for="(point, index) in displayPoints"
        :key="point.id"
        class="dock-card"
        :class="{ active: store.selectedPointId === point.id }"
      >
        <button
          class="dock-select"
          :aria-label="`在地图查看 ${point.name}`"
          :aria-pressed="store.selectedPointId === point.id"
          @click="store.selectPoint(point.id)"
        >
          <span class="dock-thumb">
            <img
              v-if="point.image"
              :src="thumbUrl(point.image)"
              :alt="point.name"
              referrerpolicy="no-referrer"
              loading="lazy"
              @load="showLoadedImage"
              @error="hideBrokenImage"
            />
            <AppIcon v-else name="image" :size="24" />
            <span class="dock-index">
              {{ String(index + 1).padStart(2, '0') }}
            </span>
            <span v-if="point.ep" class="dock-episode">EP {{ point.ep }}</span>
          </span>
          <span class="dock-caption">
            <strong>{{ point.name }}</strong>
            <span class="dock-meta">
              {{
                point.bangumiName ||
                store.bangumi?.cn ||
                store.bangumi?.title ||
                '取景地'
              }}
            </span>
          </span>
        </button>
        <button
          class="dock-save"
          :class="{ saved: store.isInLibrary(point.id) }"
          :aria-label="`${store.isInLibrary(point.id) ? '取消收藏' : '收藏'} ${point.name}`"
          :aria-pressed="store.isInLibrary(point.id)"
          @click="toggleSave(point)"
        >
          <AppIcon
            :name="store.isInLibrary(point.id) ? 'check' : 'bookmark'"
            :size="14"
          />
        </button>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { useAppStore } from '../stores/app'
import { getImageUrl } from '../utils/imageUrl'

const store = useAppStore()
const scrollRef = ref(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
const displayPoints = computed(() =>
  store.activePanel === 'history'
    ? store.historyLandmarks
    : store.activePanel === 'library' && store.coordinateLibrary.length
      ? store.coordinateLibrary
      : store.points
)
let resizeObserver
const scrollBehavior = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth'
function updateScroll() {
  const el = scrollRef.value
  if (!el) return
  canScrollLeft.value = el.scrollLeft > 2
  canScrollRight.value = el.scrollLeft < el.scrollWidth - el.clientWidth - 2
}
function scrollCards(direction) {
  scrollRef.value?.scrollBy({
    left: direction * Math.max(200, scrollRef.value.clientWidth * 0.7),
    behavior: scrollBehavior()
  })
}
function onWheel(event) {
  const el = scrollRef.value
  if (
    !el ||
    event.ctrlKey ||
    Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
    el.scrollWidth <= el.clientWidth
  )
    return
  if (
    (event.deltaY < 0 && el.scrollLeft <= 0) ||
    (event.deltaY > 0 && el.scrollLeft >= el.scrollWidth - el.clientWidth - 1)
  )
    return
  event.preventDefault()
  el.scrollLeft += event.deltaY
}
function toggleSave(point) {
  if (store.isInLibrary(point.id)) store.removeFromLibrary(point.id)
  else store.addToLibrary(point)
}
function thumbUrl(url) {
  return getImageUrl(url, 'h160')
}
function hideBrokenImage(event) {
  event.target.style.visibility = 'hidden'
}
function showLoadedImage(event) {
  event.target.style.visibility = ''
}
watch(
  () => store.selectedPointId,
  async (id) => {
    await nextTick()
    const index = displayPoints.value.findIndex((point) => point.id === id)
    const card = scrollRef.value?.children[index]
    if (card)
      scrollRef.value.scrollTo({
        left:
          card.offsetLeft -
          scrollRef.value.offsetLeft -
          (scrollRef.value.clientWidth - card.offsetWidth) / 2,
        behavior: scrollBehavior()
      })
  }
)
watch(
  displayPoints,
  async () => {
    await nextTick()
    updateScroll()
  },
  { deep: true }
)
watch(scrollRef, (element, previous) => {
  if (previous) resizeObserver?.unobserve(previous)
  if (element) resizeObserver?.observe(element)
  updateScroll()
})
onMounted(() => {
  resizeObserver = new ResizeObserver(updateScroll)
  if (scrollRef.value) resizeObserver.observe(scrollRef.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<style scoped>
.landmark-dock {
  flex-shrink: 0;
  min-width: 0;
  padding: 12px 14px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: 18px;
  box-shadow: var(--glass-shadow-sm);
}

.dock-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
}

.dock-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

.dock-header h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}

.dock-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
  background: var(--primary-soft);
  padding: 1px 8px;
  border-radius: 999px;
}

.dock-navigation {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dock-navigation .icon-button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.75);
}

.dock-navigation .icon-button:disabled {
  opacity: 0.35;
  cursor: default;
}

.dock-scroll {
  display: flex;
  position: relative;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 2px 4px;
  scrollbar-width: thin;
  overscroll-behavior-x: contain;
  scroll-snap-type: x proximity;
}

.dock-card {
  position: relative;
  flex: 0 0 180px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  overflow: hidden;
  scroll-snap-align: start;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.dock-card:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: rgba(255, 255, 255, 0.95);
}

.dock-card.active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--primary-color);
}

.dock-select {
  width: 100%;
  text-align: left;
  color: var(--text-color);
  cursor: pointer;
  border: 0;
  background: transparent;
  display: block;
}

.dock-thumb {
  position: relative;
  height: 96px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(15, 23, 42, 0.05);
  color: var(--text-muted);
  margin: 6px 6px 0;
  border-radius: 8px;
  overflow: hidden;
}

.dock-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.dock-card:hover .dock-thumb img {
  transform: scale(1.04);
}

.dock-index {
  position: absolute;
  left: 6px;
  top: 6px;
  display: grid;
  place-items: center;
  height: 22px;
  min-width: 22px;
  padding: 0 5px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  color: var(--text-color);
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
}

.dock-episode {
  position: absolute;
  left: 6px;
  bottom: 6px;
  font-size: 11px;
  font-weight: 500;
  color: #ffffff;
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(4px);
  padding: 2px 6px;
  border-radius: 5px;
}

.dock-caption {
  display: block;
  padding: 10px 34px 10px 10px;
}

.dock-caption strong {
  display: block;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.dock-meta {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.dock-save {
  position: absolute;
  right: 8px;
  bottom: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.dock-save:hover {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.dock-save.saved {
  color: var(--primary-color);
  background: var(--primary-soft);
}

@media (min-width: 1600px) {
  .dock-card {
    flex-basis: 210px;
  }
  .dock-thumb {
    height: 112px;
  }
}

@media (max-width: 820px) {
  .landmark-dock {
    padding: 10px 12px;
    border-radius: 16px;
  }
  .dock-card {
    flex-basis: 155px;
  }
  .dock-thumb {
    height: 84px;
  }
}
</style>
