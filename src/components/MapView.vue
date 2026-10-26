<template>
  <div class="map-container">
    <div
      ref="mapRef"
      class="map-element"
      aria-label="可交互的圣地巡礼地图"
    ></div>

    <div class="map-location">
      <AppIcon name="pin" :size="15" />
      <span>{{ locationLabel }}</span>
      <template v-if="mapPoints.length">
        <span class="location-separator"></span>
        <span class="location-count">{{ mapPoints.filter(hasGeo).length }} 个地标</span>
      </template>
    </div>

    <div v-if="activePlan" class="plan-map-status" :class="{ draft: !planComplete }">
      <strong>{{ planComplete ? '逐日行程' : '规划草案' }}</strong>
      <span>编号为当天访问顺序 · 连线为直线</span>
    </div>

    <div class="map-controls" aria-label="地图控制">
      <div class="zoom-controls">
        <button title="放大地图" aria-label="放大地图" @click="map?.zoomIn()">
          <AppIcon name="plus" :size="18" />
        </button>
        <button title="缩小地图" aria-label="缩小地图" @click="map?.zoomOut()">
          <AppIcon name="minus" :size="18" />
        </button>
      </div>
      <button
        title="查看全部地标"
        aria-label="查看全部地标"
        @click="fitBoundsToPoints"
      >
        <AppIcon name="target" :size="18" />
      </button>
      <button
        v-if="comparePoint"
        title="对比拍摄"
        aria-label="对比拍摄"
        @click="openComparison(comparePoint)"
      >
        <AppIcon name="camera" :size="18" />
      </button>
    </div>

    <div class="tile-switcher" aria-label="地图底图">
      <AppIcon name="layers" :size="15" />
      <button
        v-for="tile in tileOptions"
        :key="tile.key"
        :class="{ active: activeTile === tile.key }"
        :aria-pressed="activeTile === tile.key"
        @click="switchTile(tile.key)"
      >
        {{ tile.label }}
      </button>
    </div>

    <div
      v-if="store.loading && !store.planning"
      class="map-loading"
      role="status"
    >
      <span class="loading-ring"></span>
      <span>正在加载地图数据…</span>
    </div>

    <el-dialog
      v-model="comparison.open"
      title="取景对照"
      width="920px"
      append-to-body
      class="comparison-dialog"
      @closed="clearUserPhoto"
    >
      <p class="comparison-location">
        <AppIcon name="pin" :size="15" />
        {{ comparison.name }}
      </p>
      <div class="comparison-grid">
        <section class="comparison-panel">
          <header>
            <span>动画场景</span>
          </header>
          <div
            class="comparison-canvas"
            @wheel.prevent="adjustScale('animeScale', $event.deltaY)"
          >
            <img
              :src="comparison.image"
              :alt="`${comparison.name} 动画场景`"
              referrerpolicy="no-referrer"
              :style="{ transform: `scale(${comparison.animeScale / 100})` }"
            />
          </div>
          <div class="comparison-scale">
            <label for="anime-scale">缩放</label>
            <input
              id="anime-scale"
              v-model.number="comparison.animeScale"
              type="range"
              min="10"
              max="300"
            />
            <span>{{ comparison.animeScale }}%</span>
            <button class="text-button" @click="comparison.animeScale = 100">
              重置
            </button>
          </div>
        </section>

        <section class="comparison-panel">
          <header>
            <span>实景照片</span>
          </header>
          <button
            v-if="!comparison.userImage"
            class="photo-upload"
            @click="fileInput?.click()"
          >
            <span class="upload-icon">
              <AppIcon name="camera" :size="26" />
            </span>
            <strong>上传实景照片</strong>
            <span class="upload-label">
              选择照片
              <AppIcon name="plus" :size="14" />
            </span>
          </button>
          <div
            v-else
            class="comparison-canvas"
            @wheel.prevent="adjustScale('userScale', $event.deltaY)"
          >
            <img
              :src="comparison.userImage"
              :alt="`${comparison.name} 个人拍摄照片`"
              :style="{ transform: `scale(${comparison.userScale / 100})` }"
            />
            <button
              class="remove-photo icon-button"
              aria-label="移除对比照片"
              @click="clearUserPhoto"
            >
              <AppIcon name="close" :size="16" />
            </button>
          </div>
          <div class="comparison-scale">
            <label for="photo-scale">缩放</label>
            <input
              id="photo-scale"
              v-model.number="comparison.userScale"
              type="range"
              min="10"
              max="300"
              :disabled="!comparison.userImage"
            />
            <span>{{ comparison.userScale }}%</span>
            <button
              class="text-button"
              :disabled="!comparison.userImage"
              @click="comparison.userScale = 100"
            >
              重置
            </button>
          </div>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            hidden
            @change="loadPhoto"
          />
        </section>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch
} from 'vue'
import { ElMessage } from 'element-plus'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import AppIcon from './AppIcon.vue'
import { useAppStore } from '../stores/app'
import { getImageUrl } from '../utils/imageUrl'

const store = useAppStore()
const mapRef = ref(null)
const fileInput = ref(null)
let map, markersLayer, tileLayer, resizeObserver
let resizeFrame
let routeLayers = []
let markerMap = new Map()
let boundsKey = ''
let wasHidden = false
const activeTile = ref('osm')

const activePlan = computed(() =>
  store.activePanel === 'library'
    ? store.currentPlan
    : store.activePanel === 'history'
      ? store.historyPlan
      : null
)
const planComplete = computed(
  () =>
    activePlan.value?.status === 'complete' &&
    activePlan.value.validation?.passed === true
)
const mapPoints = computed(() =>
  store.activePanel === 'history'
    ? store.historyLandmarks
    : activePlan.value
      ? store.generatedLandmarks
      : store.activePanel === 'library' && store.coordinateLibrary.length
        ? store.coordinateLibrary
        : store.points
)
const locationLabel = computed(() =>
  store.activePanel === 'history'
    ? '旅途档案地图'
    : activePlan.value ||
        (store.activePanel === 'library' && store.coordinateLibrary.length)
      ? '我的巡礼地图'
      : store.bangumi?.cn || store.bangumi?.title || store.bangumi?.city || '巡礼地图'
)
const planOrder = computed(() => {
  const order = new Map()
  if (!activePlan.value) return order
  for (const day of activePlan.value.days || []) {
    const ids = day.point_ids || []
    ids.forEach((id, index) => {
      if (!order.has(String(id)))
        order.set(String(id), { day: day.day, order: index + 1 })
    })
  }
  return order
})

const dayColors = [
  '#2563eb',
  '#0ea5e9',
  '#6366f1',
  '#8b5cf6',
  '#ec4899',
  '#f59e0b',
  '#14b8a6'
]

function colorForDay(day) {
  const number = Number(day)
  return dayColors[
    (Number.isFinite(number) && number >= 1 ? number - 1 : 0) % dayColors.length
  ]
}

const comparePoint = computed(() =>
  mapPoints.value.find(
    (point) => point.id === store.selectedPointId && point.image
  )
)

const tileOptions = [
  {
    key: 'osm',
    label: '标准',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }
  },
  {
    key: 'gaode',
    label: '高德',
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    options: { maxZoom: 18, subdomains: '1234', attribution: '&copy; 高德地图' }
  }
]

const comparison = reactive({
  open: false,
  image: '',
  name: '',
  userImage: '',
  animeScale: 100,
  userScale: 100
})

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
function imageUrl(value) {
  return getImageUrl(value, 'h360')
}
function hasGeo(point) {
  return (
    Array.isArray(point.geo) &&
    point.geo.length === 2 &&
    point.geo.every(Number.isFinite) &&
    Math.abs(point.geo[0]) <= 90 &&
    Math.abs(point.geo[1]) <= 180
  )
}
function popupContent(point) {
  const image = imageUrl(point.image)
  const saved = store.isInLibrary(point.id)
  const origin = /^https?:\/\//i.test(point.originURL || '')
    ? `<a href="${escapeHtml(point.originURL)}" target="_blank" rel="noopener noreferrer">${escapeHtml(point.origin)}</a>`
    : escapeHtml(point.origin)
  const visit = planOrder.value.get(String(point.id))
  const visitLabel = visit
    ? `<span>第 ${escapeHtml(visit.day)} 天 · 第 ${escapeHtml(visit.order)} 站</span>`
    : activePlan.value
      ? '<span>未安排</span>'
      : point.day
        ? `<span>第 ${escapeHtml(point.day)} 天</span>`
        : ''
  return `<article class="landmark-popup"><h3 class="popup-title">${escapeHtml(point.name || point.cn || point.id)}</h3>${image ? `<img class="popup-image" referrerpolicy="no-referrer" src="${escapeHtml(image)}" alt="${escapeHtml(point.name || point.id)}" />` : ''}<div class="popup-meta">${point.ep ? `<span>第 ${escapeHtml(point.ep)} 集</span>` : '<span>取景地</span>'}${point.s ? `<span>${Math.floor(point.s / 60)}:${String(Math.floor(point.s % 60)).padStart(2, '0')}</span>` : ''}${visitLabel}</div>${point.origin ? `<p class="popup-origin">来源：${origin}</p>` : ''}<div class="popup-footer">${image ? `<button type="button" data-compare-id="${escapeHtml(point.id)}" class="popup-compare-btn">取景对照</button>` : ''}<button type="button" class="popup-library-btn${saved ? ' is-added' : ''}" data-point-id="${escapeHtml(point.id)}" aria-pressed="${saved}">${saved ? '✓ 已收藏' : '＋ 收藏'}</button></div></article>`
}
function createMarker(point, index) {
  const selected = point.id === store.selectedPointId
  const visit = planOrder.value.get(String(point.id))
  const checked = activePlan.value ? Boolean(visit) : point.checked !== false
  const size = selected ? 34 : checked ? 28 : 22
  const day = visit?.day || point.day
  const color =
    activePlan.value && !visit
      ? '#94a3b8'
      : day
        ? colorForDay(day)
        : '#2563eb'
  const label = activePlan.value ? visit?.order || '未' : index + 1
  return L.divIcon({
    className: 'custom-marker-wrapper',
    html: `<div class="custom-marker${selected ? ' marker-selected' : ''}" style="width:${size}px;height:${size}px;background:${color};opacity:${checked ? 1 : 0.65}">${label}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 4]
  })
}
function renderMarkers() {
  if (!map || !markersLayer) return
  const openId = [...markerMap.entries()].find(([, marker]) =>
    marker.isPopupOpen()
  )?.[0]
  markersLayer.clearLayers()
  markerMap.clear()
  mapPoints.value.forEach((point, index) => {
    if (!hasGeo(point)) return
    const marker = L.marker(point.geo, {
      icon: createMarker(point, index),
      title: point.name || point.cn || String(point.id),
      zIndexOffset: point.id === store.selectedPointId ? 1500 : 0
    })
    marker.bindPopup(popupContent(point), {
      maxWidth: 250,
      minWidth: 200,
      className: 'scene-popup',
      autoPanPaddingTopLeft: [16, 58],
      autoPanPaddingBottomRight: [48, 38]
    })
    marker.on('click', () => store.selectPoint(point.id))
    marker.addTo(markersLayer)
    markerMap.set(point.id, marker)
  })
  if (openId && markerMap.has(openId)) markerMap.get(openId).openPopup()
}
function renderRoutes() {
  if (!map) return
  routeLayers.forEach((layer) => map.removeLayer(layer))
  routeLayers = []
  const routes =
    activePlan.value || store.activePanel === 'library'
      ? store.libraryItinerary
      : store.activePanel === 'explore'
        ? store.itinerary
        : []
  routes.forEach((day, index) => {
    const coordinates = day.points.filter(hasGeo).map((point) => point.geo)
    if (coordinates.length > 1)
      routeLayers.push(
        L.polyline(coordinates, {
          color: colorForDay(day.day || index + 1),
          weight: 3,
          opacity: 0.85,
          dashArray: '6, 6'
        }).addTo(map)
      )
  })
}
function fitBoundsToPoints() {
  if (!map) return
  const valid = mapPoints.value.filter(hasGeo)
  if (!valid.length) {
    map.setView(store.defaultCenter, store.defaultZoom)
    return
  }
  if (valid.length === 1) {
    map.setView(valid[0].geo, 15)
    return
  }
  map.fitBounds(L.latLngBounds(valid.map((point) => point.geo)), {
    paddingTopLeft: [42, 70],
    paddingBottomRight: [60, 70],
    maxZoom: 16
  })
}
function focusPoint() {
  if (!map) return false
  const point = mapPoints.value.find(
    (point) => point.id === store.selectedPointId
  )
  if (!point || !hasGeo(point)) return false
  map.stop()
  map.closePopup()
  map.setView(point.geo, 16, { animate: false })
  mapPoints.value.forEach((item, index) =>
    markerMap.get(item.id)?.setIcon(createMarker(item, index))
  )
  markerMap.get(point.id)?.openPopup()
  return true
}
function switchTile(key) {
  if (activeTile.value === key || !map) return
  const tile = tileOptions.find((item) => item.key === key)
  if (!tile) return
  if (tileLayer) map.removeLayer(tileLayer)
  activeTile.value = key
  tileLayer = L.tileLayer(tile.url, tile.options).addTo(map)
}
function onMapClick(event) {
  const compareButton = event.target.closest('[data-compare-id]')
  const saveButton = event.target.closest('[data-point-id]')
  const id = compareButton?.dataset.compareId || saveButton?.dataset.pointId
  if (!id) return
  event.preventDefault()
  event.stopPropagation()
  const point = mapPoints.value.find((item) => String(item.id) === id)
  if (!point) return
  if (compareButton) openComparison(point)
  else if (store.isInLibrary(point.id)) store.removeFromLibrary(point.id)
  else store.addToLibrary(point)
}
function openComparison(point) {
  clearUserPhoto()
  comparison.image = imageUrl(point.image)
  comparison.name = point.name
  comparison.animeScale = 100
  comparison.open = true
}
function clearUserPhoto() {
  if (comparison.userImage) URL.revokeObjectURL(comparison.userImage)
  comparison.userImage = ''
  comparison.userScale = 100
}
function loadPhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    event.target.value = ''
    return
  }
  clearUserPhoto()
  comparison.userImage = URL.createObjectURL(file)
  event.target.value = ''
}
function adjustScale(key, delta) {
  comparison[key] = Math.max(
    10,
    Math.min(300, comparison[key] + (delta > 0 ? -5 : 5))
  )
}

watch(
  mapPoints,
  async () => {
    await nextTick()
    renderMarkers()
    renderRoutes()
    const key = mapPoints.value
      .filter(hasGeo)
      .map((point) => `${point.id}:${point.geo}`)
      .join('|')
    if (key !== boundsKey) {
      boundsKey = key
      fitBoundsToPoints()
    }
  },
  { deep: true }
)
watch(
  () => [store.libraryItinerary, store.itinerary, store.activePanel],
  renderRoutes,
  { deep: true }
)
watch(activePlan, () => {
  renderMarkers()
  renderRoutes()
})
watch(() => store.mapFocusRequest, focusPoint, { flush: 'post' })
watch(
  () => store.coordinateLibrary,
  () => {
    mapPoints.value.forEach((point) =>
      markerMap.get(point.id)?.setPopupContent(popupContent(point))
    )
  },
  { deep: true }
)
watch(
  () => store.compareData,
  (data) => {
    if (data) {
      openComparison(data)
      store.compareData = null
    }
  }
)
onMounted(async () => {
  await nextTick()
  if (!mapRef.value) return
  map = L.map(mapRef.value, {
    center: store.defaultCenter,
    zoom: store.defaultZoom,
    zoomControl: false,
    attributionControl: true
  })
  map.attributionControl.setPrefix(false)
  tileLayer = L.tileLayer(tileOptions[0].url, tileOptions[0].options).addTo(map)
  markersLayer = L.layerGroup().addTo(map)
  mapRef.value.addEventListener('click', onMapClick)
  renderMarkers()
  renderRoutes()
  if (mapPoints.value.length) fitBoundsToPoints()
  resizeObserver = new ResizeObserver((entries) => {
    const { width, height } = entries[0].contentRect
    if (!width || !height) {
      wasHidden = true
      return
    }
    cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(() => {
      if (!map) return
      mapRef.value.style.setProperty(
        '--popup-max-height',
        `${Math.max(64, Math.min(320, height - 124))}px`
      )
      map.invalidateSize({ pan: false })
      if (wasHidden) {
        if (!focusPoint()) fitBoundsToPoints()
        wasHidden = false
      }
      markerMap.forEach((marker) => {
        if (marker.isPopupOpen()) marker.getPopup().update()
      })
    })
  })
  resizeObserver.observe(mapRef.value)
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  cancelAnimationFrame(resizeFrame)
  mapRef.value?.removeEventListener('click', onMapClick)
  clearUserPhoto()
  map?.remove()
  map = null
})
</script>

<style scoped>
.map-container,
.map-element {
  width: 100%;
  height: 100%;
  position: relative;
}

.map-element {
  z-index: 0;
}

.map-element :deep(.leaflet-popup-content) {
  max-height: var(--popup-max-height, 320px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.map-location {
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-color);
  font-size: 13px;
  font-weight: 500;
  box-shadow: var(--glass-shadow-sm);
  z-index: 500;
}

.map-location > svg {
  color: var(--primary-color);
}

.location-separator {
  height: 12px;
  width: 1px;
  background: var(--border-color);
}

.location-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
}

.plan-map-status {
  position: absolute;
  top: 62px;
  left: 16px;
  z-index: 500;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: min(340px, calc(100% - 100px));
  padding: 8px 12px;
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  box-shadow: var(--glass-shadow-sm);
  color: var(--primary-color);
  font-size: 12px;
}

.plan-map-status.draft {
  color: #d97706;
}

.plan-map-status span {
  color: var(--text-secondary);
  font-size: 11px;
}

.map-controls {
  position: absolute;
  right: 16px;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 500;
}

.map-controls button {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-color);
  box-shadow: var(--glass-shadow-sm);
  cursor: pointer;
  transition: all 0.18s ease;
}

.map-controls button:hover {
  background: #ffffff;
  color: var(--primary-color);
}

.zoom-controls {
  border: 1px solid var(--glass-border);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--glass-shadow-sm);
}

.zoom-controls button {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.zoom-controls button + button {
  border-top: 1px solid var(--border-color);
}

.tile-switcher {
  position: absolute;
  left: 16px;
  bottom: 16px;
  display: flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  padding: 4px;
  border-radius: 10px;
  z-index: 500;
  box-shadow: var(--glass-shadow-sm);
}

.tile-switcher > svg {
  margin: 0 6px;
  color: var(--text-secondary);
}

.tile-switcher button {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  border: 0;
  border-radius: 7px;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.tile-switcher button.active {
  background: var(--primary-soft);
  color: var(--primary-color);
  font-weight: 600;
}

.map-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  white-space: nowrap;
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: 14px;
  box-shadow: var(--glass-shadow);
  z-index: 600;
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-color);
}

.loading-ring {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(37, 99, 235, 0.2);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

:deep(.popup-title) {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  margin: 0 0 10px;
  color: var(--text-color);
}

:deep(.popup-image) {
  display: block;
  width: 100%;
  max-height: 150px;
  object-fit: cover;
  border-radius: 8px;
}

:deep(.popup-meta) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

:deep(.popup-origin) {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  margin: 4px 0 0;
}

:deep(.popup-origin a) {
  color: var(--primary-color);
  text-decoration: none;
}

:deep(.popup-footer) {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

:deep(.popup-footer button) {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 7px 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.15s ease;
}

:deep(.popup-footer button:hover) {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

:deep(.popup-footer .popup-library-btn) {
  color: #ffffff;
  background: var(--primary-color);
  border-color: var(--primary-color);
}

:deep(.popup-footer .popup-library-btn:hover) {
  background: var(--primary-hover);
  color: #ffffff;
}

:deep(.popup-footer .is-added) {
  background: var(--primary-soft);
  color: var(--primary-color);
  border-color: rgba(37, 99, 235, 0.2);
}

.comparison-location {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  margin: -8px 0 18px;
}

.comparison-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.comparison-panel {
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.65);
  overflow: hidden;
  min-width: 0;
}

.comparison-panel > header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
  border-bottom: 1px solid var(--border-color);
}

.comparison-canvas {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  height: min(44vh, 380px);
  overflow: auto;
  background: rgba(15, 23, 42, 0.03);
  padding: 12px;
  position: relative;
}

.comparison-canvas img {
  display: block;
  max-width: 100%;
  transform-origin: top center;
  border-radius: 6px;
}

.comparison-scale {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  color: var(--text-secondary);
  font-size: 12px;
  border-top: 1px solid var(--border-color);
}

.comparison-scale input {
  flex: 1;
  min-width: 40px;
  accent-color: var(--primary-color);
}

.comparison-scale > span {
  min-width: 38px;
  font-variant-numeric: tabular-nums;
}

.photo-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: min(44vh, 380px);
  border: 0;
  background: rgba(15, 23, 42, 0.02);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease;
}

.photo-upload:hover {
  background: var(--primary-soft);
}

.upload-icon {
  border-radius: 50%;
  padding: 16px;
  background: var(--primary-soft);
  color: var(--primary-color);
  display: flex;
  margin-bottom: 14px;
}

.photo-upload strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}

.upload-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.85);
  border-radius: 8px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--primary-color);
  font-weight: 500;
}

.remove-photo {
  position: sticky;
  top: 0;
  right: 0;
  margin-left: -36px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-color);
}

@media (max-width: 820px) {
  .plan-map-status {
    top: 56px;
    left: 12px;
    max-width: calc(100% - 72px);
  }
  .map-location {
    top: 12px;
    left: 12px;
    padding: 8px 12px;
    font-size: 12px;
  }
  .map-controls {
    right: 12px;
    top: 12px;
  }
  .map-controls button {
    width: 34px;
    height: 34px;
  }
  .tile-switcher {
    left: 12px;
    bottom: 16px;
  }
  .comparison-grid {
    grid-template-columns: 1fr;
  }
  .comparison-canvas,
  .photo-upload {
    height: 230px;
  }
}
</style>
