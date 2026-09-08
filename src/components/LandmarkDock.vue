<template>
  <section
    v-if="displayPoints.length"
    class="landmark-dock"
    aria-label="场景地标列表"
  >
    <header class="dock-header">
      <div>
        <AppIcon name="camera" :size="16" />
        <h2>
          {{
            store.activePanel === 'library'
              ? '我的场景收藏'
              : '每一帧，都有迹可循'
          }}
        </h2>
        <span class="dock-count">{{ displayPoints.length }} 个地标</span>
      </div>
      <div class="dock-navigation">
        <button
          class="icon-button"
          :disabled="!canScrollLeft"
          aria-label="向前浏览地标"
          @click="scrollCards(-1)"
        >
          <AppIcon name="back" :size="16" /></button
        ><button
          class="icon-button"
          :disabled="!canScrollRight"
          aria-label="向后浏览地标"
          @click="scrollCards(1)"
        >
          <AppIcon name="arrow" :size="16" />
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
          <span class="dock-thumb"
            ><img
              v-if="point.image"
              :src="thumbUrl(point.image)"
              :alt="point.name"
              loading="lazy"
              @error="hideBrokenImage"
            /><AppIcon v-else name="image" :size="27" /><span
              class="dock-index"
              >{{ String(index + 1).padStart(2, '0') }}</span
            ><span v-if="point.ep" class="dock-episode"
              >EP. {{ point.ep }}</span
            ></span
          >
          <span class="dock-caption"
            ><strong>{{ point.name }}</strong
            ><small
              ><AppIcon name="pin" :size="10" />{{
                point.bangumiName ||
                store.bangumi?.cn ||
                store.bangumi?.title ||
                '动画取景地'
              }}</small
            ></span
          >
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
  <section v-else class="journey-steps" aria-label="巡礼使用指南">
    <div class="steps-heading">
      <span class="eyebrow">YOUR FIRST PILGRIMAGE</span>
      <h2>把喜欢，写成一段旅程。</h2>
    </div>
    <div class="journey-step">
      <span>01</span>
      <div>
        <strong>找到你的故事</strong>
        <p>搜索喜欢的动画作品</p>
      </div>
      <AppIcon name="search" :size="18" />
    </div>
    <div class="journey-step">
      <span>02</span>
      <div>
        <strong>收集心动坐标</strong>
        <p>收藏想亲自抵达的风景</p>
      </div>
      <AppIcon name="bookmark" :size="18" />
    </div>
    <div class="journey-step">
      <span>03</span>
      <div>
        <strong>让旅程发生</strong>
        <p>交给 AI，串起你的巡礼</p>
      </div>
      <AppIcon name="sparkles" :size="18" />
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const scrollRef = ref(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
const displayPoints = computed(() =>
  store.activePanel === 'library' && store.coordinateLibrary.length
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
  return url.includes('?') ? url : `${url}?plan=h160`
}
function hideBrokenImage(event) {
  event.target.style.visibility = 'hidden'
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
}
.dock-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 1px 10px;
}
.dock-header > div {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #738569;
}
.dock-header h2 {
  font-size: 12px;
  font-weight: 550;
  color: var(--text-color);
}
.dock-count {
  font-size: 9px;
  color: #8c977e;
  border-left: 1px solid #dde2d2;
  padding-left: 8px;
  margin-left: 2px;
}
.dock-navigation {
  gap: 5px !important;
}
.dock-navigation .icon-button {
  width: 25px;
  height: 25px;
  border: 1px solid #dce2d3;
  border-radius: 6px;
  background: var(--surface-color);
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
  padding: 2px 2px 8px;
  scrollbar-width: thin;
  overscroll-behavior-x: contain;
  scroll-snap-type: x proximity;
}
.dock-card {
  position: relative;
  flex: 0 0 175px;
  border: 1px solid #e0e4d7;
  border-radius: 10px;
  background: var(--surface-color);
  overflow: hidden;
  scroll-snap-align: start;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}
.dock-card:hover {
  border-color: #a5b396;
  box-shadow: 0 3px 8px #36492b09;
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
  height: 94px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #e0e8d7;
  color: #9baa8c;
  margin: 5px 5px 0;
  border-radius: 6px;
  overflow: hidden;
}
.dock-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
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
  height: 21px;
  min-width: 21px;
  background: #fffef9eb;
  color: #526949;
  font-size: 10px;
  border-radius: 4px;
}
.dock-episode {
  position: absolute;
  left: 6px;
  bottom: 6px;
  font-size: 7px;
  letter-spacing: 0.6px;
  color: #fff;
  background: #2e462c99;
  padding: 3px 5px;
  border-radius: 3px;
}
.dock-caption {
  display: block;
  padding: 10px 31px 10px 10px;
}
.dock-caption strong {
  display: block;
  font-size: 11px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.6;
}
.dock-caption small {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-top: 3px;
  font-size: 8px;
  color: #8a967d;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.dock-save {
  position: absolute;
  right: 8px;
  bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 23px;
  height: 26px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #8e9c81;
  cursor: pointer;
}
.dock-save:hover {
  background: #eaf0e2;
  color: var(--primary-color);
}
.dock-save.saved {
  color: var(--primary-color);
  background: #eaf0e2;
}
.journey-steps {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr 1fr;
  align-items: center;
  gap: 15px;
  padding: 22px 4px 17px;
  flex-shrink: 0;
}
.steps-heading .eyebrow {
  font-size: 7px;
  letter-spacing: 1.4px;
  color: #929c83;
}
.steps-heading h2 {
  font-size: 13px;
  font-weight: 500;
  margin-top: 9px;
}
.journey-step {
  display: flex;
  align-items: center;
  gap: 10px;
  border-left: 1px solid #dde3d3;
  padding-left: 17px;
}
.journey-step > span {
  font-family: Georgia, serif;
  font-size: 23px;
  color: #acb59b;
  font-style: italic;
}
.journey-step strong {
  font-size: 10px;
  font-weight: 550;
  display: block;
}
.journey-step p {
  font-size: 8px;
  color: #929b84;
  margin-top: 6px;
  white-space: nowrap;
}
.journey-step > svg {
  display: none;
}
@media (min-width: 1600px) {
  .dock-card {
    flex-basis: 210px;
  }
  .dock-thumb {
    height: 118px;
  }
  .dock-caption strong {
    font-size: 12px;
  }
  .journey-step {
    gap: 17px;
    padding-left: 25px;
  }
  .journey-step strong {
    font-size: 12px;
  }
  .journey-step p {
    font-size: 10px;
  }
  .steps-heading h2 {
    font-size: 15px;
  }
}
@media (max-width: 1200px) {
  .journey-steps {
    grid-template-columns: repeat(3, 1fr);
    padding-top: 14px;
    padding-bottom: 10px;
    gap: 10px;
  }
  .steps-heading {
    display: none;
  }
  .journey-step {
    padding-left: 12px;
    gap: 8px;
  }
  .journey-step:nth-child(2) {
    padding-left: 0;
    border: 0;
  }
}
@media (max-width: 820px) {
  .dock-header h2 {
    font-size: 11px;
  }
  .dock-count {
    font-size: 8px;
  }
  .dock-card {
    flex-basis: 150px;
  }
  .dock-thumb {
    height: 82px;
  }
  .dock-scroll {
    gap: 9px;
    padding-bottom: 5px;
  }
  .dock-caption {
    padding: 8px 28px 9px 9px;
  }
  .dock-header {
    padding-bottom: 7px;
  }
  .journey-steps {
    gap: 6px;
    padding: 12px 0 8px;
  }
  .journey-step {
    gap: 6px;
    padding-left: 9px;
    align-items: flex-start;
  }
  .journey-step > span {
    font-size: 19px;
  }
  .journey-step strong {
    font-size: 9px;
    padding-top: 2px;
  }
  .journey-step p {
    font-size: 8px;
    white-space: normal;
    line-height: 1.6;
  }
}
</style>
