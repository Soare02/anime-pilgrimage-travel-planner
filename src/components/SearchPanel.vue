<template>
  <section class="search-panel">
    <header class="panel-hero">
      <h1>探索圣地坐标</h1>
      <p>检索动画作品，在地图中还原真实取景地</p>
    </header>

    <div class="search-card">
      <form class="search-form" role="search" @submit.prevent="handleSearch">
        <div class="search-field">
          <AppIcon name="search" :size="18" />
          <input
            id="anime-search"
            v-model="searchText"
            type="search"
            placeholder="搜索作品名称或 Bangumi ID"
            aria-label="搜索动画作品"
            autocomplete="off"
            :disabled="loading"
            @input="handleInput"
          />
          <button
            type="submit"
            :disabled="loading || searching || !searchText.trim()"
            aria-label="搜索作品"
          >
            <AppIcon v-if="!searching" name="arrow" :size="17" />
            <span v-else class="small-spinner"></span>
          </button>
        </div>
      </form>

      <div class="quick-tags">
        <button
          v-for="tag in quickTags"
          :key="tag.name"
          type="button"
          class="quick-tag"
          :disabled="loading"
          @click="selectAnime(tag.id, tag.name)"
        >
          {{ tag.name }}
        </button>
      </div>
    </div>

    <div v-if="error" class="search-error" role="alert">
      <el-alert :title="error" type="error" show-icon :closable="false" />
    </div>

    <section
      v-if="searchResults.length || searching || (hasSearched && !error)"
      class="search-results"
      aria-live="polite"
    >
      <div class="section-heading">
        <h2>
          搜索结果 <span>{{ searchResults.length }}</span>
        </h2>
        <button class="text-button" @click="closeResults">收起</button>
      </div>
      <p v-if="!searchResults.length && !searching" class="no-results">
        未找到相关作品，请尝试其他名称或输入 Bangumi ID。
      </p>
      <div class="result-list">
        <button
          v-for="item in searchResults"
          :key="item.id"
          class="result-item"
          :disabled="loading"
          @click="selectAnime(item.id, item.name_cn || item.name)"
        >
          <span class="result-cover">
            <img
              v-if="item.image"
              :src="getImageUrl(item.image, 'h160')"
              :alt="item.name_cn || item.name"
              referrerpolicy="no-referrer"
              loading="lazy"
              @load="showLoadedImage"
              @error="hideBrokenImage"
            />
            <AppIcon v-else name="image" :size="20" />
          </span>
          <span class="result-info">
            <strong>{{ item.name_cn || item.name }}</strong>
            <span class="result-meta">
              {{ item.air_date || '动画作品' }} · ID {{ item.id }}
            </span>
          </span>
          <AppIcon name="chevron" :size="16" />
        </button>
      </div>
    </section>

    <div
      v-if="loading && !store.libraryAiResponse"
      class="loading-note"
      role="status"
    >
      <span class="small-spinner"></span>
      <span>正在加载取景地数据…</span>
    </div>

    <template v-if="bangumi">
      <section class="current-anime">
        <div class="section-heading">
          <h2>当前作品</h2>
          <button class="text-button" :disabled="loading" @click="resetExplore">
            返回推荐
          </button>
        </div>
        <div class="anime-card">
          <div class="anime-card-top">
            <div class="anime-cover">
              <img
                v-if="bangumi.cover"
                :src="getImageUrl(bangumi.cover, 'h160')"
                :alt="bangumi.cn || bangumi.title"
                referrerpolicy="no-referrer"
                @load="showLoadedImage"
                @error="hideBrokenImage"
              />
              <AppIcon v-else name="image" :size="22" />
            </div>
            <div class="anime-details">
              <h3>{{ bangumi.cn || bangumi.title }}</h3>
              <p v-if="bangumi.title && bangumi.title !== bangumi.cn" class="anime-sub">
                {{ bangumi.title }}
              </p>
              <span class="anime-city">
                <AppIcon name="pin" :size="13" />
                {{ bangumi.city || '日本' }}
              </span>
            </div>
          </div>
          <div class="anime-stats-grid">
            <div class="stat-box">
              <strong>{{ points.length }}</strong>
              <span>场景地标</span>
            </div>
            <div class="stat-box">
              <strong>{{ savedCount }}</strong>
              <span>已收藏</span>
            </div>
          </div>
        </div>
      </section>

      <section v-if="points.length" class="scenes-section">
        <div class="section-heading">
          <h2>取景地标列表</h2>
          <button
            class="text-button"
            :disabled="savedCount === points.length"
            @click="collectAll"
          >
            {{ savedCount === points.length ? '已全部收藏' : '全部收藏' }}
            <AppIcon v-if="savedCount !== points.length" name="plus" :size="14" />
          </button>
        </div>
        <div class="scene-list">
          <div
            v-for="(point, index) in points"
            :key="point.id"
            class="scene-row"
            :class="{ selected: selectedPointId === point.id }"
          >
            <button class="scene-select" @click="focusPoint(point)">
              <span class="scene-number">
                {{ String(index + 1).padStart(2, '0') }}
              </span>
              <span class="scene-name">
                <strong>{{ point.name }}</strong>
                <span class="scene-meta">
                  {{ point.ep ? `第 ${point.ep} 集` : '取景地' }}
                  <template v-if="point.s"> · {{ formatTime(point.s) }}</template>
                </span>
              </span>
            </button>
            <button
              class="scene-save icon-button"
              :class="{ saved: store.isInLibrary(point.id) }"
              :aria-label="`${store.isInLibrary(point.id) ? '取消收藏' : '收藏'} ${point.name}`"
              :aria-pressed="store.isInLibrary(point.id)"
              @click="toggleSave(point)"
            >
              <AppIcon
                :name="store.isInLibrary(point.id) ? 'check' : 'plus'"
                :size="16"
              />
            </button>
          </div>
        </div>
      </section>
      <p v-else-if="!loading" class="no-results">
        该作品暂无可展示的场景地标。
      </p>
    </template>

    <template
      v-else-if="!searchResults.length && !searching && (!hasSearched || error)"
    >
      <section class="recommendations">
        <div class="section-heading">
          <h2>热门巡礼作品</h2>
          <button
            type="button"
            class="text-button"
            :disabled="loading"
            @click="exploreRandom"
          >
            <AppIcon name="sparkles" :size="14" />
            随机探索
          </button>
        </div>
        <div class="recommendation-list">
          <button
            v-for="anime in recommendations"
            :key="anime.id"
            class="recommendation-card"
            :disabled="loading"
            @click="selectAnime(anime.id, anime.name)"
          >
            <span class="recommendation-cover">
              <img
                :src="getImageUrl(anime.cover, 'h160')"
                :alt="anime.name"
                referrerpolicy="no-referrer"
                loading="lazy"
                @load="showLoadedImage"
                @error="hideBrokenImage"
              />
            </span>
            <span class="recommendation-info">
              <strong>{{ anime.name }}</strong>
              <span v-if="anime.scenes" class="recommendation-scenes">
                {{ anime.scenes }}
              </span>
              <span class="recommendation-location">
                <AppIcon name="pin" :size="12" />
                {{ anime.location }}
              </span>
            </span>
            <span class="recommendation-arrow">
              <AppIcon name="chevron" :size="16" />
            </span>
          </button>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import AppIcon from './AppIcon.vue'
import { recommendations } from '../utils/recommendations'
import { getImageUrl } from '../utils/imageUrl'
import { useAppStore } from '../stores/app'

const emit = defineEmits(['show-map'])
const store = useAppStore()
const {
  bangumi,
  points,
  selectedPointId,
  loading,
  searching,
  error,
  searchResults
} = storeToRefs(store)
const searchText = ref('')
const hasSearched = ref(false)
const quickTags = [
  { id: 160209, name: '你的名字。' },
  { id: 328609, name: '孤独摇滚！' },
  { id: 117777, name: '声之形' },
  { id: 269235, name: '天气之子' }
]
const savedCount = computed(
  () => points.value.filter((point) => store.isInLibrary(point.id)).length
)
let searchTimer
let searchVersion = 0

function handleInput(event) {
  clearTimeout(searchTimer)
  searchVersion++
  hasSearched.value = false
  store.clearSearchResults()
  if (event?.isComposing) return
  const value = searchText.value.trim()
  if (!value || /^\d+$/.test(value)) return
  searchTimer = setTimeout(handleSearch, 450)
}
async function handleSearch() {
  clearTimeout(searchTimer)
  const value = searchText.value.trim()
  if (!value || loading.value) return
  if (/^\d+$/.test(value)) return selectAnime(value, value)
  const version = ++searchVersion
  await store.searchByKey(value)
  if (version === searchVersion) hasSearched.value = true
}
async function selectAnime(id, name) {
  clearTimeout(searchTimer)
  searchVersion++
  if (loading.value) return
  searchText.value = name
  hasSearched.value = false
  store.clearSearchResults()
  try {
    await store.searchBangumi(id)
    emit('show-map')
  } catch {
    // Error is displayed via store.error
  }
}
function exploreRandom() {
  const randomItem =
    recommendations[Math.floor(Math.random() * recommendations.length)]
  if (randomItem) {
    selectAnime(randomItem.id, randomItem.name)
  }
}
function closeResults() {
  clearTimeout(searchTimer)
  searchVersion++
  hasSearched.value = false
  store.clearSearchResults()
}
function resetExplore() {
  closeResults()
  store.reset()
  searchText.value = ''
}
function focusPoint(point) {
  store.selectPoint(point.id)
  emit('show-map')
}
function toggleSave(point) {
  if (store.isInLibrary(point.id)) store.removeFromLibrary(point.id)
  else store.addToLibrary(point)
}
function collectAll() {
  const previous = savedCount.value
  points.value.forEach((point) => store.addToLibrary(point))
  ElMessage.success(`已收藏 ${savedCount.value - previous} 个场景地标`)
}
function hideBrokenImage(event) {
  event.target.style.visibility = 'hidden'
}
function showLoadedImage(event) {
  event.target.style.visibility = ''
}
function formatTime(seconds) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  store.clearSearchResults()
})
</script>

<style scoped>
.search-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.panel-hero {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-hero h1 {
  font-size: 19px;
  font-weight: 600;
  color: var(--text-color);
  letter-spacing: 0.3px;
}

.panel-hero p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.search-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.03);
}

.search-form {
  margin: 0;
}

.search-field {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding: 4px 5px 4px 13px;
  border: 1px solid var(--border-color);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.search-field:focus-within {
  border-color: var(--primary-color);
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.search-field > svg {
  flex-shrink: 0;
}

.search-field input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  font-size: 14px;
  outline: 0;
  color: var(--text-color);
}

.search-field input::placeholder {
  color: var(--text-muted);
}

.search-field button {
  border: 0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  background: var(--primary-color);
  color: #ffffff;
  cursor: pointer;
  transition: background 0.18s ease;
}

.search-field button:hover:not(:disabled) {
  background: var(--primary-hover);
}

.search-field button:disabled {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-muted);
  cursor: default;
}

.quick-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.quick-tag {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background: rgba(255, 255, 255, 0.78);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.quick-tag:hover:not(:disabled) {
  color: var(--primary-color);
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(37, 99, 235, 0.06);
}

.search-error :deep(.el-alert) {
  border-radius: 10px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.section-heading h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
}

.section-heading h2 > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  margin-left: 4px;
}

.recommendation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.recommendation-card {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 11px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.68);
  border-radius: 15px;
  text-align: left;
  cursor: pointer;
  color: var(--text-color);
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.03);
  transition: all 0.2s ease;
}

.recommendation-card:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
}

.recommendation-card:disabled {
  opacity: 0.55;
}

.recommendation-cover {
  width: 58px;
  height: 76px;
  border-radius: 9px;
  flex-shrink: 0;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.05);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
}

.recommendation-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.recommendation-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
}

.recommendation-info > strong {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text-color);
}

.recommendation-scenes {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.recommendation-location {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--primary-color);
  background: rgba(37, 99, 235, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
}

.recommendation-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: all 0.18s ease;
}

.recommendation-card:hover .recommendation-arrow {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-item {
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.65);
  width: 100%;
  padding: 10px;
  display: flex;
  text-align: left;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.18s ease;
}

.result-item:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(37, 99, 235, 0.25);
}

.result-cover {
  display: grid;
  place-items: center;
  width: 44px;
  height: 58px;
  background: rgba(15, 23, 42, 0.05);
  border-radius: 7px;
  overflow: hidden;
  flex-shrink: 0;
}

.result-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.result-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-info strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-color);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-meta {
  font-size: 12px;
  color: var(--text-secondary);
}

.no-results {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.loading-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--primary-color);
  font-size: 13px;
  padding: 12px 0;
}

.small-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(37, 99, 235, 0.2);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.anime-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.9);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
}

.anime-card-top {
  display: flex;
  align-items: center;
  gap: 14px;
}

.anime-cover {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 62px;
  height: 86px;
  overflow: hidden;
  border-radius: 9px;
  background: rgba(15, 23, 42, 0.05);
}

.anime-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.anime-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
}

.anime-details h3 {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-color);
}

.anime-sub {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.anime-city {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--primary-color);
  background: var(--primary-soft);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}

.anime-stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

.stat-box {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.03);
}

.stat-box strong {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-color);
}

.stat-box span {
  font-size: 12px;
  color: var(--text-secondary);
}

.scene-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.scene-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 5px 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.scene-row:hover {
  background: rgba(255, 255, 255, 0.88);
  border-color: rgba(15, 23, 42, 0.06);
}

.scene-row.selected {
  background: var(--primary-soft);
  border-color: rgba(37, 99, 235, 0.22);
}

.scene-select {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  text-align: left;
  gap: 12px;
  padding: 6px 2px;
  border: 0;
  background: none;
  color: var(--text-color);
  cursor: pointer;
}

.scene-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.05);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.scene-row.selected .scene-number {
  background: var(--primary-color);
  color: #ffffff;
}

.scene-name {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.scene-name strong {
  display: block;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-meta {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
}

.scene-save {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  flex-shrink: 0;
}

.scene-save.saved {
  background: var(--primary-color);
  color: #ffffff;
  border-color: var(--primary-color);
}
</style>
