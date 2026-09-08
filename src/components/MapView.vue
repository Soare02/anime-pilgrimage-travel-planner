<template>
  <div class="map-container" :class="{ 'is-empty': !mapPoints.length }">
    <div
      ref="mapRef"
      class="map-element"
      aria-label="可交互的圣地巡礼地图"
    ></div>
    <div class="map-location">
      <AppIcon name="pin" :size="14" /><span>{{ locationLabel }}</span
      ><span class="location-separator"></span
      ><small>{{
        mapPoints.length ? `${mapPoints.length} 个坐标` : 'JAPAN'
      }}</small>
    </div>

    <template v-if="!mapPoints.length && !store.loading">
      <div class="map-welcome">
        <span>WANDER INTO A STORY</span>
        <h3>下一站，<br />心动的那一帧。</h3>
        <p>在真实的世界，与喜欢的故事重逢。</p>
      </div>
      <button
        class="map-postcard"
        :disabled="store.loading"
        @click="startJourney"
      >
        <JourneyArtwork /><span class="postcard-caption"
          ><span
            ><small>A LITTLE INSPIRATION</small
            ><strong>给下一次出发，一个理由</strong></span
          ><span class="postcard-arrow"
            ><AppIcon name="arrow" :size="18" /></span
        ></span>
      </button>
      <span class="map-coordinate" aria-hidden="true"
        >35°40′ N &nbsp; 139°45′ E<br /><small
          >EVERY SCENE IS A DESTINATION</small
        ></span
      >
    </template>

    <div class="map-controls" aria-label="地图控制">
      <div class="zoom-controls">
        <button title="放大地图" aria-label="放大地图" @click="map?.zoomIn()">
          <AppIcon name="plus" :size="18" /></button
        ><button title="缩小地图" aria-label="缩小地图" @click="map?.zoomOut()">
          <AppIcon name="minus" :size="18" />
        </button>
      </div>
      <button
        title="查看全部地标"
        aria-label="查看全部地标"
        @click="fitBoundsToPoints"
      >
        <AppIcon name="target" :size="19" />
      </button>
      <button
        v-if="comparePoint"
        title="对比拍摄"
        aria-label="对比拍摄"
        @click="openComparison(comparePoint)"
      >
        <AppIcon name="camera" :size="19" />
      </button>
    </div>
    <div class="tile-switcher" aria-label="地图底图">
      <AppIcon name="layers" :size="15" /><button
        v-for="tile in tileOptions"
        :key="tile.key"
        :class="{ active: activeTile === tile.key }"
        :aria-pressed="activeTile === tile.key"
        @click="switchTile(tile.key)"
      >
        {{ tile.label }}
      </button>
    </div>
    <div v-if="mapPoints.length" class="map-legend">
      <span class="legend-dot"></span
      ><span>{{
        store.activePanel === 'library' ? '我的收藏坐标' : '动画取景地'
      }}</span
      ><span class="legend-count">{{ mapPoints.length }}</span>
    </div>
    <div
      v-if="store.loading && !store.planning"
      class="map-loading"
      role="status"
    >
      <span class="loading-ring"></span><span>正在寻找故事的坐标</span>
    </div>

    <el-dialog
      v-model="comparison.open"
      title="取景对照"
      width="960px"
      append-to-body
      class="comparison-dialog"
      @closed="clearUserPhoto"
    >
      <p class="comparison-location">
        <AppIcon name="pin" :size="14" />{{ comparison.name }}
      </p>
      <div class="comparison-grid">
        <section class="comparison-panel">
          <header><span>动画中的这一帧</span><small>ANIME SCENE</small></header>
          <div
            class="comparison-canvas"
            @wheel.prevent="adjustScale('animeScale', $event.deltaY)"
          >
            <img
              :src="comparison.image"
              :alt="`${comparison.name} 动画场景`"
              :style="{ transform: `scale(${comparison.animeScale / 100})` }"
            />
          </div>
          <div class="comparison-scale">
            <label for="anime-scale">缩放</label
            ><input
              id="anime-scale"
              v-model.number="comparison.animeScale"
              type="range"
              min="10"
              max="300"
            /><span>{{ comparison.animeScale }}%</span
            ><button class="text-button" @click="comparison.animeScale = 100">
              重置
            </button>
          </div>
        </section>
        <section class="comparison-panel">
          <header><span>你的镜头</span><small>YOUR PHOTO</small></header>
          <button
            v-if="!comparison.userImage"
            class="photo-upload"
            @click="fileInput?.click()"
          >
            <span><AppIcon name="camera" :size="28" /></span
            ><strong>放入你拍下的风景</strong
            ><small>选择一张照片，试试还原相同的构图</small
            ><span class="upload-label"
              >选择照片 <AppIcon name="plus" :size="14"
            /></span>
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
            /><button
              class="remove-photo icon-button"
              aria-label="移除对比照片"
              @click="clearUserPhoto"
            >
              <AppIcon name="close" :size="16" />
            </button>
          </div>
          <div class="comparison-scale">
            <label for="photo-scale">缩放</label
            ><input
              id="photo-scale"
              v-model.number="comparison.userScale"
              type="range"
              min="10"
              max="300"
              :disabled="!comparison.userImage"
            /><span>{{ comparison.userScale }}%</span
            ><button
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
      <p class="comparison-tip">
        调整画面比例，找到故事与现实重叠的瞬间。照片仅在当前浏览器中用于对比。
      </p>
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
import JourneyArtwork from './JourneyArtwork.vue'
import { useAppStore } from '../stores/app'
import { recommendations } from '../utils/recommendations'

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
const mapPoints = computed(() =>
  store.activePanel === 'library' && store.coordinateLibrary.length
    ? store.coordinateLibrary
    : store.points
)
const locationLabel = computed(() =>
  store.activePanel === 'library' && store.coordinateLibrary.length
    ? '我的巡礼地图'
    : store.bangumi?.city || '日本 · 东京'
)
const comparePoint = computed(() =>
  mapPoints.value.find(
    (point) => point.id === store.selectedPointId && point.image
  )
)
const dayColors = [
  '#3c614b',
  '#75917b',
  '#bc955d',
  '#ba7766',
  '#82939d',
  '#9687a5',
  '#729e9c'
]
const tileOptions = [
  {
    key: 'osm',
    label: '街道',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
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
  return /^https?:\/\//i.test(value || '')
    ? value.replace(/([?&])plan=h\d+/, '$1plan=h360')
    : ''
}
function hasGeo(point) {
  return (
    Array.isArray(point.geo) &&
    point.geo.length === 2 &&
    point.geo.every(Number.isFinite)
  )
}
function popupContent(point) {
  const image = imageUrl(point.image)
  const saved = store.isInLibrary(point.id)
  const origin = /^https?:\/\//i.test(point.originURL || '')
    ? `<a href="${escapeHtml(point.originURL)}" target="_blank" rel="noopener noreferrer">${escapeHtml(point.origin)}</a>`
    : escapeHtml(point.origin)
  return `<article class="landmark-popup"><span class="popup-eyebrow">SCENE LOCATION</span><h3 class="popup-title">${escapeHtml(point.name)}</h3>${image ? `<img class="popup-image" src="${escapeHtml(image)}" alt="${escapeHtml(point.name)}" />` : ''}<div class="popup-meta">${point.ep ? `<span>第 ${escapeHtml(point.ep)} 集</span>` : '<span>动画取景地</span>'}${point.s ? `<span>${Math.floor(point.s / 60)}:${String(Math.floor(point.s % 60)).padStart(2, '0')}</span>` : ''}${point.day ? `<span>第 ${escapeHtml(point.day)} 天</span>` : ''}</div>${point.origin ? `<p class="popup-origin">场景来源 · ${origin}</p>` : ''}<div class="popup-footer">${image ? `<button type="button" data-compare-id="${escapeHtml(point.id)}" class="popup-compare-btn">取景对照</button>` : ''}<button type="button" class="popup-library-btn${saved ? ' is-added' : ''}" data-point-id="${escapeHtml(point.id)}" aria-pressed="${saved}">${saved ? '✓ 已收藏' : '＋ 收藏坐标'}</button></div></article>`
}
function createMarker(point, index) {
  const selected = point.id === store.selectedPointId
  const checked = point.checked !== false
  const size = selected ? 36 : checked ? 30 : 23
  return L.divIcon({
    className: 'custom-marker-wrapper',
    html: `<div class="custom-marker${selected ? ' marker-selected' : ''}" style="width:${size}px;height:${size}px;background:${point.day ? dayColors[(point.day - 1) % 7] : '#3c614b'};opacity:${checked ? 1 : 0.5}">${index + 1}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 5]
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
      title: point.name,
      zIndexOffset: point.id === store.selectedPointId ? 1500 : 0
    })
    marker.bindPopup(popupContent(point), {
      maxWidth: 240,
      minWidth: 190,
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
    store.activePanel === 'library' ? store.libraryItinerary : store.itinerary
  routes.forEach((day, index) => {
    const coordinates = day.points.filter(hasGeo).map((point) => point.geo)
    if (coordinates.length > 1)
      routeLayers.push(
        L.polyline(coordinates, {
          color: dayColors[index % 7],
          weight: 3,
          opacity: 0.8,
          dashArray: '7, 7'
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
  if (!map) return
  const point = mapPoints.value.find(
    (point) => point.id === store.selectedPointId
  )
  if (!point || !hasGeo(point)) return
  // Finish any previous pan before the popup calculates its available space.
  map.stop()
  map.closePopup()
  map.setView(point.geo, 16, { animate: false })
  mapPoints.value.forEach((item, index) =>
    markerMap.get(item.id)?.setIcon(createMarker(item, index))
  )
  markerMap.get(point.id)?.openPopup()
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
async function startJourney() {
  if (store.loading) return
  store.activePanel = 'explore'
  try {
    await store.searchBangumi(recommendations[0].id)
  } catch {
    /* SearchPanel displays the error. */
  }
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
        fitBoundsToPoints()
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
.map-container.is-empty::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 400;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    rgba(246, 247, 236, 0.96),
    rgba(246, 247, 236, 0.8) 30%,
    rgba(246, 247, 236, 0.16) 70%,
    transparent
  );
}
.map-element :deep(.leaflet-tile-pane) {
  filter: saturate(0.65) sepia(0.1);
}
.map-element :deep(.leaflet-popup-content) {
  max-height: var(--popup-max-height, 320px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.map-location {
  position: absolute;
  top: 20px;
  left: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border: 1px solid #e2e6db;
  border-radius: 9px;
  background: #fffef9f0;
  color: #51634b;
  font-size: 11px;
  box-shadow: 0 3px 12px #2b402a08;
  z-index: 500;
}
.map-location small {
  font-size: 9px;
  letter-spacing: 1px;
  color: #8c9680;
}
.location-separator {
  height: 12px;
  width: 1px;
  background: #dfe4d5;
  margin: 0 3px;
}
.map-welcome {
  position: absolute;
  left: 33px;
  top: 95px;
  pointer-events: none;
  z-index: 450;
}
.map-welcome > span {
  color: #768569;
  font-size: 8px;
  font-weight: 650;
  letter-spacing: 2px;
}
.map-welcome h3 {
  font-size: clamp(25px, 2.7vw, 40px);
  line-height: 1.45;
  font-weight: 550;
  letter-spacing: 3px;
  color: #3b533e;
  margin-top: 12px;
  text-shadow:
    0 1px 10px #fffef9,
    0 1px 30px #fffef9;
}
.map-welcome p {
  margin-top: 13px;
  font-size: 11px;
  color: #6c7d61;
  text-shadow: 0 1px 7px #fffef9;
}
.map-postcard {
  position: absolute;
  left: 30px;
  bottom: 68px;
  width: clamp(220px, 24vw, 300px);
  border: 6px solid #fffef9;
  border-radius: 3px;
  background: #fffef9;
  color: var(--text-color);
  transform: rotate(-3deg);
  box-shadow: 0 6px 20px #2b43291c;
  cursor: pointer;
  text-align: left;
  z-index: 460;
  transition:
    transform 0.25s,
    box-shadow 0.25s;
}
.map-postcard:hover {
  transform: rotate(0deg) translateY(-3px);
  box-shadow: 0 10px 28px #2b43292b;
}
.map-postcard > svg {
  display: block;
  width: 100%;
  height: auto;
}
.postcard-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 9px 8px;
}
.postcard-caption small {
  display: block;
  font-size: 7px;
  letter-spacing: 1.5px;
  color: #89957c;
}
.postcard-caption strong {
  display: block;
  font-size: 11px;
  margin-top: 6px;
  font-weight: 500;
}
.postcard-arrow {
  display: flex;
  background: #edf1e5;
  padding: 8px;
  border-radius: 50%;
  color: var(--primary-color);
}
.map-coordinate {
  position: absolute;
  right: 28px;
  top: 30px;
  text-align: right;
  color: #8c9c88;
  font-family: Georgia, serif;
  font-size: 15px;
  line-height: 1.9;
  pointer-events: none;
  z-index: 450;
}
.map-coordinate small {
  font-family: var(--el-font-family);
  font-size: 6px;
  letter-spacing: 1.4px;
}
.map-controls {
  position: absolute;
  right: 18px;
  top: 110px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  z-index: 500;
}
.map-controls button {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dde2d5;
  border-radius: 8px;
  background: #fffef9f5;
  color: #5b7051;
  box-shadow: 0 2px 7px #2b402a07;
  cursor: pointer;
}
.map-controls button:hover {
  background: #e9eee0;
  color: var(--primary-color);
}
.zoom-controls {
  border: 1px solid #dde2d5;
  border-radius: 8px;
  overflow: hidden;
}
.zoom-controls button {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.zoom-controls button + button {
  border-top: 1px solid #e6e9dc;
}
.tile-switcher {
  position: absolute;
  left: 20px;
  bottom: 20px;
  display: flex;
  align-items: center;
  gap: 3px;
  border: 1px solid #dce3d2;
  background: #fffef9f0;
  padding: 4px;
  border-radius: 8px;
  z-index: 500;
  box-shadow: 0 2px 7px #2b402a07;
}
.tile-switcher > svg {
  margin: 0 7px 0 5px;
  color: #829176;
}
.tile-switcher button {
  padding: 7px 11px;
  font-size: 10px;
  border: 0;
  border-radius: 5px;
  background: none;
  color: #7a866f;
  cursor: pointer;
}
.tile-switcher button.active {
  background: #e7eddf;
  color: #3c614b;
  font-weight: 600;
}
.map-legend {
  position: absolute;
  right: 20px;
  bottom: 30px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 11px;
  border-radius: 8px;
  background: #fffef9e8;
  font-size: 9px;
  color: #758468;
  z-index: 450;
}
.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-color);
}
.legend-count {
  font-size: 10px;
  color: var(--primary-color);
  padding-left: 5px;
  border-left: 1px solid #dfe5d6;
}
.map-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 24px;
  white-space: nowrap;
  background: #fffef9f5;
  border: 1px solid #dce3d2;
  border-radius: 12px;
  box-shadow: 0 6px 24px #30493215;
  z-index: 600;
  font-size: 12px;
  color: var(--primary-color);
}
.loading-ring {
  width: 18px;
  height: 18px;
  border: 2px solid #d8e2cf;
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
:deep(.popup-eyebrow) {
  font-size: 8px;
  letter-spacing: 1.5px;
  color: #929e86;
}
:deep(.popup-title) {
  font-size: 14px;
  line-height: 1.5;
  margin: 5px 0 10px;
  color: var(--text-color);
}
:deep(.popup-image) {
  display: block;
  width: 100%;
  max-height: 155px;
  object-fit: cover;
  border-radius: 7px;
}
:deep(.popup-meta) {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 6px;
  font-size: 10px;
  color: var(--text-secondary);
}
:deep(.popup-origin) {
  font-size: 8px;
  line-height: 1.5;
  color: #98a28c;
  margin: 5px 0 0;
}
:deep(.popup-origin a) {
  color: #728a65;
}
:deep(.popup-footer) {
  display: flex;
  gap: 7px;
  margin-top: 12px;
}
:deep(.popup-footer button) {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  font-family: inherit;
  font-size: 10px;
  padding: 8px 9px;
  border: 1px solid #d6e0cc;
  border-radius: 6px;
  background: #f2f5ec;
  color: var(--primary-color);
  cursor: pointer;
}
:deep(.popup-footer .popup-library-btn) {
  color: #fffef9;
  background: var(--primary-color);
  border-color: var(--primary-color);
}
:deep(.popup-footer .is-added) {
  background: #e7eddf;
  color: var(--primary-color);
  border-color: #d6e0cc;
}
.comparison-location {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  margin: -12px 0 22px;
}
.comparison-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.comparison-panel {
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
.comparison-panel > header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 15px;
  font-size: 12px;
  color: var(--text-color);
}
.comparison-panel > header small {
  font-size: 8px;
  color: #96a088;
  letter-spacing: 1.2px;
}
.comparison-canvas {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  height: min(45vh, 400px);
  overflow: auto;
  background: #edf0e7;
  padding: 12px;
  position: relative;
}
.comparison-canvas img {
  display: block;
  max-width: 100%;
  transform-origin: top center;
}
.comparison-scale {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px;
  color: var(--text-secondary);
  font-size: 10px;
}
.comparison-scale input {
  flex: 1;
  min-width: 40px;
  accent-color: var(--primary-color);
}
.comparison-scale > span {
  min-width: 34px;
  font-variant-numeric: tabular-nums;
}
.photo-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: min(45vh, 400px);
  border: 0;
  border-top: 1px dashed #d5ddca;
  border-bottom: 1px dashed #d5ddca;
  background: #f0f3e9;
  color: #839576;
  cursor: pointer;
}
.photo-upload > span:first-child {
  border-radius: 50%;
  padding: 20px;
  background: #e5ebdb;
  display: flex;
  margin-bottom: 18px;
}
.photo-upload strong {
  font-size: 14px;
  font-weight: 550;
  color: #5d7551;
}
.photo-upload small {
  font-size: 10px;
  margin-top: 10px;
}
.upload-label {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border: 1px solid #c7d3bb;
  border-radius: 7px;
  margin-top: 20px;
  font-size: 11px;
}
.photo-upload:hover {
  background: #e9eede;
}
.remove-photo {
  position: sticky;
  top: 0;
  right: 0;
  margin-left: -34px;
  flex-shrink: 0;
  background: #fffef9dd;
  color: var(--text-color);
}
.comparison-tip {
  margin-top: 18px;
  color: #939d87;
  font-size: 10px;
  line-height: 1.8;
}
@media (max-height: 820px) and (min-width: 821px) {
  .map-welcome h3 {
    font-size: 28px;
  }
  .map-welcome {
    top: 85px;
    left: 26px;
  }
  .map-welcome p {
    display: none;
  }
  .map-postcard {
    width: 218px;
    bottom: 64px;
    left: 28px;
  }
  .postcard-caption {
    padding: 8px 6px 4px;
  }
}
@media (max-width: 1100px) {
  .map-coordinate {
    display: none;
  }
  .map-welcome h3 {
    font-size: 27px;
  }
  .map-postcard {
    width: 215px;
  }
  .map-welcome {
    left: 24px;
  }
}
@media (max-width: 820px) {
  .map-location {
    top: 13px;
    left: 12px;
    padding: 9px 11px;
    font-size: 10px;
  }
  .map-controls {
    right: 12px;
    top: 66px;
  }
  .map-controls button {
    width: 33px;
    height: 33px;
  }
  .map-welcome {
    top: 72px;
    left: 23px;
  }
  .map-welcome h3 {
    font-size: 26px;
    margin-top: 8px;
  }
  .map-welcome p {
    display: none;
  }
  .map-postcard {
    width: 185px;
    bottom: 60px;
    left: 25px;
  }
  .postcard-caption {
    padding: 8px 5px 4px;
  }
  .postcard-caption strong {
    font-size: 9px;
  }
  .postcard-caption small {
    font-size: 6px;
  }
  .postcard-arrow {
    padding: 6px;
  }
  .tile-switcher {
    left: 12px;
    bottom: 22px;
  }
  .map-legend {
    right: 12px;
    bottom: 26px;
    padding: 8px;
  }
  .comparison-grid {
    grid-template-columns: 1fr;
  }
  .comparison-canvas,
  .photo-upload {
    height: 230px;
  }
}
@media (max-height: 720px) and (max-width: 820px) {
  .map-postcard {
    display: none;
  }
  .map-welcome h3 {
    font-size: 23px;
  }
}
</style>
