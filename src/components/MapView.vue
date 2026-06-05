<template>
  <div class="map-container">
    <div ref="mapRef" class="map-element"></div>

    <div class="tile-switcher">
      <button
        v-for="t in tileOptions"
        :key="t.key"
        class="tile-btn"
        :class="{ active: activeTile === t.key }"
        @click="switchTile(t.key)"
      >{{ t.label }}</button>
    </div>
    <button
      v-if="comparePoint"
      class="compare-trigger-btn"
      title="对比拍摄"
      @click="openComparison(comparePoint)"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
    </button>

    <teleport to="body">
    <div v-if="compareMode" class="compare-overlay" @click.self="closeComparison">
      <div class="compare-modal">
        <button class="compare-modal-close" @click="closeComparison">&times;</button>
        <div class="compare-modal-body">
          <div class="compare-ctrl-strip">
            <div class="compare-ctrl-group">
              <span class="ctrl-group-label">动漫</span>
              <div class="ctrl-group-btns">
                <button class="ctrl-btn" @click="adjustCompareScale(-0.01)">−</button>
                <span class="ctrl-pct">{{ compareScale }}%</span>
                <button class="ctrl-btn" @click="adjustCompareScale(0.01)">+</button>
                <button class="ctrl-btn" @click="compareScale = 100">重置</button>
              </div>
              <input type="range" min="10" max="300" v-model.number="compareScale" class="ctrl-slider" />
            </div>
            <div class="compare-ctrl-group" v-if="compareUserImage">
              <span class="ctrl-group-label">拍摄</span>
              <div class="ctrl-group-btns">
                <button class="ctrl-btn" @click="adjustCompareUserScale(-0.01)">−</button>
                <span class="ctrl-pct">{{ compareUserScale }}%</span>
                <button class="ctrl-btn" @click="adjustCompareUserScale(0.01)">+</button>
                <button class="ctrl-btn" @click="compareUserScale = 100">重置</button>
              </div>
              <input type="range" min="10" max="300" v-model.number="compareUserScale" class="ctrl-slider" />
            </div>
          </div>
          <div class="compare-images">
            <div class="compare-col">
              <div class="compare-col-img">
                <img :src="compareApiImage" :style="compareTopStyle" @wheel.prevent="onCompareWheel" />
              </div>
            </div>
            <div class="compare-col">
              <div class="compare-col-img compare-col-upload" @click="triggerCompareUpload" v-if="!compareUserImage">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>点击上传照片</span>
              </div>
              <div class="compare-col-img" v-else>
                <img :src="compareUserImage" :style="compareUserStyle" @wheel.prevent="onCompareUserWheel" />
                <button class="compare-remove-photo" @click="compareUserImage = ''">&times;</button>
              </div>
              <input ref="compareFileInput" type="file" accept="image/*" @change="onCompareUpload" hidden />
            </div>
          </div>
        </div>
      </div>
    </div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app'
import { storeToRefs } from 'pinia'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const store = useAppStore()
const { points, selectedPointId, libraryItinerary, defaultCenter, defaultZoom, bangumi, loading, coordinateLibrary } = storeToRefs(store)

const mapRef = ref(null)
let map = null
let markersLayer = null
let routeLayers = []
let markerMap = {}
let tileLayer = null

const tileOptions = [
  {
    key: 'carto',
    label: 'CartoDB',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    options: { maxZoom: 19, subdomains: 'abcd', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>' }
  },
  {
    key: 'gaode',
    label: '高德',
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    options: { maxZoom: 18, subdomains: '1234', attribution: '&copy; 高德地图' }
  }
]
const activeTile = ref('carto')

const compareMode = ref(false)
const compareApiImage = ref('')
const compareName = ref('')
const compareUserImage = ref('')
const compareScale = ref(100)
const compareUserScale = ref(100)
const compareFileInput = ref(null)

const comparePoint = computed(() => {
  const id = selectedPointId.value
  if (!id) return null
  const pt = points.value.find(p => p.id === id)
  return pt && pt.image ? pt : null
})

const compareTopStyle = computed(() => {
  const s = compareScale.value / 100
  return { transform: `scale(${s})`, transformOrigin: 'top center' }
})

const compareUserStyle = computed(() => {
  const s = compareUserScale.value / 100
  return { transform: `scale(${s})`, transformOrigin: 'top center' }
})

const dayColors = [
  '#409EFF',
  '#67C23A',
  '#E6A23C',
  '#F56C6C',
  '#909399',
  '#b37feb',
  '#36cfc9'
]

function createMarkerIcon(index, day, checked) {
  const color = day ? dayColors[(day - 1) % dayColors.length] : '#409EFF'
  const opacity = checked ? 1 : 0.3
  const size = checked ? 30 : 22
  const fontSize = checked ? 14 : 10
  const borderW = checked ? 2 : 1
  return L.divIcon({
    className: 'custom-marker-wrapper',
    html: `<div class="custom-marker${checked ? '' : ' marker-unchecked'}" style="background-color:${color};opacity:${opacity};width:${size}px;height:${size}px;font-size:${fontSize}px;border-width:${borderW}px">${index + 1}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2 - 4]
  })
}

const escapeHtml = (s) => {
  if (!s) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const safeUrl = (url) => {
  if (!url) return ''
  return /^https?:\/\//.test(url) ? escapeHtml(url) : ''
}

function createPopupContent(point) {
  const name = escapeHtml(point.name)
  const inLibrary = store.isInLibrary(point.id)
  let html = `<div class="landmark-popup">`
  html += `<div class="popup-title">${name}</div>`
  if (point.image) {
    const imgUrl = point.image.includes('?') ? point.image : point.image + '?plan=h360'
    html += `<img src="${escapeHtml(imgUrl)}" alt="${name}" class="popup-image" />`
  }
  html += `<div class="popup-info">`
  if (point.ep) html += `<span>EP${escapeHtml(String(point.ep))}</span>`
  if (point.s) html += `<span>${escapeHtml(formatTime(point.s))}</span>`
  if (point.day) html += `<span class="popup-day">第${escapeHtml(String(point.day))}天</span>`
  html += `</div>`
  if (point.origin) {
    html += `<div class="popup-origin">来源: `
    if (point.originURL) {
      const url = safeUrl(point.originURL)
      html += url
        ? `<a href="${url}" target="_blank" rel="noopener">${escapeHtml(point.origin)}</a>`
        : escapeHtml(point.origin)
    } else {
      html += escapeHtml(point.origin)
    }
    html += `</div>`
  }
  const btnStyle = inLibrary
    ? 'background:rgba(255,215,0,0.2);color:#FFD700;border-color:rgba(255,215,0,0.4)'
    : ''
  const icon = inLibrary ? '&#9733;' : '&#9734;'
  const label = inLibrary ? '已收藏' : '收藏'
  const showCompare = point.image ? '' : 'style="display:none"'
  html += `<div class="popup-footer">`
  html += `<button class="popup-compare-btn" data-compare-id="${point.id}" ${showCompare}>对比</button>`
  html += `<button class="popup-library-btn ${inLibrary ? 'is-added' : ''}" data-point-id="${point.id}" style="${btnStyle}">${icon} ${label}</button>`
  html += `</div></div>`
  return html
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

function openComparison(point) {
  const rawUrl = point.image || ''
  compareApiImage.value = rawUrl.includes('?') ? rawUrl : rawUrl + '?plan=h360'
  compareName.value = point.name
  compareUserImage.value = ''
  compareScale.value = 100
  compareMode.value = true
}

function closeComparison() {
  compareMode.value = false
  compareUserImage.value = ''
}

function adjustCompareScale(delta) {
  let v = compareScale.value + delta * 100
  if (v < 10) v = 10
  if (v > 300) v = 300
  compareScale.value = Math.round(v)
}

function triggerCompareUpload() {
  compareFileInput.value?.click()
}

function onCompareUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    compareUserImage.value = ev.target.result
  }
  reader.readAsDataURL(file)
  e.target.value = ''
}

function onCompareWheel(e) {
  const delta = e.deltaY > 0 ? -1 : 1
  adjustCompareScale(delta / 100)
}

function adjustCompareUserScale(delta) {
  let v = compareUserScale.value + delta * 100
  if (v < 10) v = 10
  if (v > 300) v = 300
  compareUserScale.value = Math.round(v)
}

function onCompareUserWheel(e) {
  const delta = e.deltaY > 0 ? -1 : 1
  adjustCompareUserScale(delta / 100)
}

function initMap() {
  if (!mapRef.value) return

  map = L.map(mapRef.value, {
    center: defaultCenter.value,
    zoom: defaultZoom.value,
    zoomControl: true,
    attributionControl: false
  })

  tileLayer = L.tileLayer(tileOptions[0].url, tileOptions[0].options).addTo(map)

  markersLayer = L.layerGroup().addTo(map)

  mapRef.value.addEventListener('click', (e) => {
    const compareBtn = e.target.closest('.popup-compare-btn')
    if (compareBtn) {
      e.preventDefault()
      e.stopPropagation()
      const pointId = compareBtn.dataset.compareId
      const point = points.value.find(p => p.id === pointId)
      if (point) openComparison(point)
      return
    }
    const libBtn = e.target.closest('.popup-library-btn')
    if (!libBtn) return
    e.preventDefault()
    e.stopPropagation()
    const pointId = libBtn.dataset.pointId
    if (!pointId) return
    if (store.isInLibrary(pointId)) {
      store.removeFromLibrary(pointId)
    } else {
      const point = points.value.find(p => p.id === pointId)
      if (point) store.addToLibrary(point)
    }
  })
}

function switchTile(key) {
  const opt = tileOptions.find(t => t.key === key)
  if (!opt || !map) return
  activeTile.value = key
  if (tileLayer) map.removeLayer(tileLayer)
  tileLayer = L.tileLayer(opt.url, opt.options).addTo(map)
}

function updateMarkers() {
  if (!map || !markersLayer) return

  markersLayer.clearLayers()
  markerMap = {}

  points.value.forEach((point, index) => {
    if (!point.geo || point.geo.length !== 2) return

    const icon = createMarkerIcon(index, point.day, point.checked)
    const marker = L.marker([point.geo[0], point.geo[1]], { icon, zIndexOffset: point.checked ? 1000 : 0 })
    
    marker.bindPopup(createPopupContent(point), {
      maxWidth: 300,
      className: 'custom-popup'
    })

    marker.on('click', () => {
      store.selectPoint(point.id)
    })

    markersLayer.addLayer(marker)
    markerMap[point.id] = marker
  })
}

function updateRoutes() {
  routeLayers.forEach(layer => {
    if (map.hasLayer(layer)) {
      map.removeLayer(layer)
    }
  })
  routeLayers = []

  const routeData = libraryItinerary.value
  if (!routeData || routeData.length === 0) return

  routeData.forEach((dayPlan, index) => {
    if (dayPlan.points.length < 2) return

    const color = dayColors[index % dayColors.length]
    const latlngs = dayPlan.points.map(p => [p.geo[0], p.geo[1]])

    const polyline = L.polyline(latlngs, {
      color: color,
      weight: 3,
      opacity: 0.8,
      dashArray: '8, 6'
    }).addTo(map)

    routeLayers.push(polyline)
  })
}

function fitBoundsToPoints() {
  if (!map || points.value.length === 0) return

  const validPoints = points.value.filter(p => p.geo && p.geo.length === 2)
  if (validPoints.length === 0) return

  if (validPoints.length === 1) {
    map.setView([validPoints[0].geo[0], validPoints[0].geo[1]], 14)
    return
  }

  const bounds = L.latLngBounds(validPoints.map(p => [p.geo[0], p.geo[1]]))
  map.fitBounds(bounds, { padding: [40, 40] })
}

function focusPoint(pointId) {
  const point = points.value.find(p => p.id === pointId)
  if (!point || !point.geo || !map) return

  map.setView([point.geo[0], point.geo[1]], 16, { animate: true })

  const marker = markerMap[pointId]
  if (marker) {
    marker.openPopup()
  }
}

watch(points, () => {
  nextTick(() => {
    updateMarkers()
    updateRoutes()
    if (points.value.length > 0) {
      fitBoundsToPoints()
    }
  })
}, { deep: true })

watch(libraryItinerary, () => {
  nextTick(() => {
    updateMarkers()
    updateRoutes()
    if (libraryItinerary.value.length > 0) {
      fitBoundsToPoints()
    }
  })
}, { deep: true })

watch(selectedPointId, (newId) => {
  if (newId) {
    focusPoint(newId)
  }
})

watch(defaultCenter, () => {
  if (map && bangumi.value) {
    map.setView(defaultCenter.value, defaultZoom.value, { animate: true })
  }
})

watch(coordinateLibrary, () => {
  if (!map) return
  const container = map.getContainer()
  if (!container) return
  const btns = container.querySelectorAll('.popup-library-btn')
  btns.forEach(btn => {
    const pid = btn.dataset.pointId
    if (!pid) return
    const inLib = store.isInLibrary(pid)
    if (inLib) {
      btn.style.background = 'rgba(255,215,0,0.2)'
      btn.style.color = '#FFD700'
      btn.style.borderColor = 'rgba(255,215,0,0.4)'
      btn.innerHTML = '&#9733; 已收藏'
      btn.classList.add('is-added')
    } else {
      btn.style.background = ''
      btn.style.color = ''
      btn.style.borderColor = ''
      btn.innerHTML = '&#9734; 收藏'
      btn.classList.remove('is-added')
    }
  })
}, { deep: true })

watch(() => store.compareData, (data) => {
  if (data) {
    const point = { image: data.image, name: data.name }
    openComparison(point)
    store.compareData = null
  }
})

onMounted(() => {
  nextTick(() => {
    initMap()
  })
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.map-container {
  flex: 1;
  position: relative;
  height: 100%;
}

.map-element {
  width: 100%;
  height: 100%;
}

.map-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--text-color);
  z-index: 1000;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 20px 30px;
  border-radius: 12px;
}

.custom-marker-wrapper {
  background: none;
  border: none;
}

:deep(.custom-marker) {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background-color: var(--primary-color);
  color: white;
  font-weight: bold;
  border: 2px solid white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  text-align: center;
  line-height: 1;
  transition: opacity 0.2s, width 0.2s, height 0.2s;
}

:deep(.marker-unchecked) {
  border-color: rgba(255, 255, 255, 0.6);
  box-shadow: none;
}

:deep(.custom-popup .leaflet-popup-content-wrapper) {
  background: rgba(255, 255, 255, 0.8) !important;
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.4);
  color: var(--text-color);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
}

:deep(.custom-popup .leaflet-popup-tip) {
  background: rgba(255, 255, 255, 0.8) !important;
  backdrop-filter: blur(20px);
}

:deep(.custom-popup .leaflet-popup-content) {
  margin: 12px;
  font-size: 14px;
  line-height: 1.5;
}

:deep(.custom-popup .landmark-popup) {
  min-width: 180px;
  max-width: 260px;
}

:deep(.custom-popup .popup-title) {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
  margin-bottom: 8px;
}

:deep(.custom-popup .popup-image) {
  width: 100%;
  max-height: 160px;
  object-fit: cover;
  border-radius: 6px;
  margin-bottom: 8px;
}

:deep(.custom-popup .popup-info) {
  display: flex;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

:deep(.custom-popup .popup-day) {
  color: var(--primary-color);
  font-weight: 500;
}

:deep(.custom-popup .popup-origin) {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}

:deep(.custom-popup .popup-origin a) {
  color: var(--primary-color);
  text-decoration: none;
}

:deep(.custom-popup .popup-origin a:hover) {
  text-decoration: underline;
}

:deep(.custom-popup .popup-footer) {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

:deep(.custom-popup .popup-library-btn) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 14px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: rgba(0, 0, 0, 0.02);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
}

:deep(.custom-popup .popup-library-btn:hover) {
  background: rgba(9, 105, 218, 0.08);
  border-color: rgba(9, 105, 218, 0.35);
  color: var(--primary-color);
}

:deep(.custom-popup .popup-library-btn.is-added) {
  background: rgba(255, 215, 0, 0.12) !important;
  color: #b08d00 !important;
  border-color: rgba(255, 215, 0, 0.4) !important;
}

.tile-switcher {
  position: absolute;
  bottom: 290px;
  right: 20px;
  z-index: 1000;
  display: flex;
  gap: 2px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.tile-btn {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}

.tile-btn:hover {
  background: rgba(9, 105, 218, 0.06);
  color: var(--primary-color);
}

.tile-btn.active {
  background: var(--primary-color);
  color: white;
}

/* Compare trigger button — below zoom controls */
.compare-trigger-btn {
  position: absolute;
  top: 88px;
  left: 390px;
  z-index: 1000;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transition: all 0.15s;
}

.compare-trigger-btn:hover {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

/* Compare overlay */
.compare-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.compare-modal {
  width: 57vw;
  height: 92vh;
  max-width: 960px;
  max-height: 1200px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(25px) saturate(180%);
  -webkit-backdrop-filter: blur(25px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.15);
  position: relative;
}

.compare-modal-close {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 10;
  width: 26px;
  height: 26px;
  border: none;
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.compare-modal-close:hover {
  background: rgba(255, 80, 80, 0.8);
}

.compare-modal-body {
  flex: 1;
  display: flex;
  gap: 0;
  min-height: 0;
}

/* Left control strip */
.compare-ctrl-strip {
  width: 48px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  padding: 8px 6px;
  gap: 12px;
  overflow-y: auto;
}

.compare-ctrl-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.ctrl-group-label {
  font-size: 9px;
  color: var(--text-secondary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.ctrl-group-btns {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.ctrl-btn {
  width: 28px;
  height: 20px;
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  border-radius: 3px;
  font-family: inherit;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}

.ctrl-btn:hover {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: white;
}

.ctrl-pct {
  font-size: 9px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1;
}

.ctrl-slider {
  writing-mode: vertical-lr;
  direction: rtl;
  width: 16px;
  height: 100px;
  accent-color: var(--primary-color);
  cursor: pointer;
}

/* Image columns */
.compare-images {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.compare-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.compare-col:first-child {
  border-bottom: 1px solid var(--border-color);
}

.compare-col-img {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 8px;
  min-height: 0;
  background: rgba(0, 0, 0, 0.03);
  position: relative;
}

.compare-col-img img {
  max-width: 100%;
  display: block;
  transition: transform 0.1s ease;
}

.compare-col-img.compare-col-upload {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  transition: background 0.15s;
}

.compare-col-img.compare-col-upload:hover {
  background: rgba(9, 105, 218, 0.06);
}

.compare-remove-photo {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  border: none;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  font-size: 14px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.compare-col-img:hover .compare-remove-photo {
  opacity: 1;
}

/* Popup compare button */
:deep(.popup-compare-btn) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid rgba(9, 105, 218, 0.25);
  background: rgba(9, 105, 218, 0.06);
  color: var(--primary-color);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  margin-right: 4px;
}

:deep(.popup-compare-btn:hover) {
  background: rgba(9, 105, 218, 0.15);
  border-color: var(--primary-color);
}
</style>
