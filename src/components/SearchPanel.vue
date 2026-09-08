<template>
  <section class="search-panel">
    <div class="search-intro">
      <span class="eyebrow"
        ><span class="tiny-line"></span> A JOURNEY INTO ANIME</span
      >
      <h1>去故事里，<br />见一面<span class="title-dot">。</span></h1>
      <p>寻找动画中的真实风景，<br />收藏下一段旅程的坐标。</p>
      <span class="intro-stamp" aria-hidden="true">旅<small>たび</small></span>
    </div>

    <form class="search-form" role="search" @submit.prevent="handleSearch">
      <label for="anime-search" class="search-label">想从哪部作品出发？</label>
      <div class="search-field">
        <AppIcon name="search" :size="18" />
        <input
          id="anime-search"
          v-model="searchText"
          type="search"
          placeholder="作品名称 / Bangumi ID"
          autocomplete="off"
          :disabled="loading"
          @input="handleInput"
        />
        <button
          type="submit"
          :disabled="loading || searching || !searchText.trim()"
          aria-label="搜索作品"
        >
          <AppIcon v-if="!searching" name="arrow" :size="18" /><span
            v-else
            class="small-spinner"
          ></span>
        </button>
      </div>
      <div class="search-hint">
        <span>{{
          searching ? '正在寻找作品…' : '输入名称自动搜索，也可以直接输入 ID'
        }}</span
        ><kbd>↵</kbd>
      </div>
    </form>

    <div v-if="error" class="search-error" role="alert">
      <el-alert :title="error" type="error" show-icon :closable="false" />
      <p v-if="hasSearched">可以直接输入 Bangumi ID，或从下方推荐作品出发。</p>
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
        暂时没有找到这部作品，换个名称或试试 Bangumi ID。
      </p>
      <button
        v-for="item in searchResults"
        :key="item.id"
        class="result-item"
        :disabled="loading"
        @click="selectAnime(item.id, item.name_cn || item.name)"
      >
        <span class="result-cover"
          ><img
            v-if="item.image"
            :src="item.image"
            :alt="item.name_cn || item.name"
            loading="lazy"
            @error="hideBrokenImage" /><AppIcon v-else name="image" :size="22"
        /></span>
        <span class="result-info"
          ><strong>{{ item.name_cn || item.name }}</strong
          ><small v-if="item.name_cn && item.name !== item.name_cn">{{
            item.name
          }}</small
          ><span
            >{{ item.air_date || '动画作品' }}<i>·</i>{{ item.id }}</span
          ></span
        >
        <AppIcon name="chevron" :size="16" />
      </button>
    </section>

    <div
      v-if="loading && !store.libraryAiResponse"
      class="loading-note"
      role="status"
    >
      <span class="small-spinner"></span>正在展开这部作品的巡礼地图…
    </div>

    <template v-if="bangumi">
      <section class="current-anime">
        <div class="section-heading">
          <h2>正在探索</h2>
          <button class="text-button" :disabled="loading" @click="resetExplore">
            换部作品 <AppIcon name="arrow" :size="13" />
          </button>
        </div>
        <div class="anime-card">
          <div class="anime-cover">
            <img
              v-if="bangumi.cover"
              :src="bangumi.cover"
              :alt="bangumi.cn || bangumi.title"
              @error="hideBrokenImage"
            /><AppIcon v-else name="image" :size="24" />
          </div>
          <div class="anime-details">
            <span class="eyebrow">NOW EXPLORING</span>
            <h2>{{ bangumi.cn || bangumi.title }}</h2>
            <p v-if="bangumi.title !== bangumi.cn">{{ bangumi.title }}</p>
            <span class="anime-city"
              ><AppIcon name="pin" :size="12" />{{
                bangumi.city || '巡礼目的地'
              }}</span
            >
          </div>
        </div>
        <div class="anime-stats">
          <span
            ><strong>{{ points.length }}</strong> 个场景坐标</span
          ><span
            ><strong>{{ savedCount }}</strong> 个已收藏</span
          >
        </div>
      </section>
      <section v-if="points.length" class="scenes-section">
        <div class="section-heading">
          <h2>这一帧，在这里</h2>
          <button
            class="text-button"
            :disabled="savedCount === points.length"
            @click="collectAll"
          >
            {{ savedCount === points.length ? '已全部收藏' : '收藏全部'
            }}<AppIcon name="plus" :size="13" />
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
              <span class="scene-number">{{
                String(index + 1).padStart(2, '0')
              }}</span
              ><span class="scene-name"
                ><strong>{{ point.name }}</strong
                ><small
                  >{{ point.ep ? `第 ${point.ep} 集` : '动画取景地'
                  }}<template v-if="point.s">
                    · {{ formatTime(point.s) }}</template
                  ></small
                ></span
              >
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
        这部作品还没有带场景图片的地标，试试探索其他作品。
      </p>
    </template>

    <template
      v-else-if="!searchResults.length && !searching && (!hasSearched || error)"
    >
      <section class="recommendations">
        <div class="section-heading">
          <h2>从这些故事开始</h2>
          <span class="section-caption">PICK A STORY</span>
        </div>
        <button
          v-for="(anime, index) in recommendations"
          :key="anime.id"
          class="recommendation-card"
          :class="anime.color"
          :disabled="loading"
          @click="selectAnime(anime.id, anime.name)"
        >
          <span class="recommendation-cover"
            ><img
              :src="anime.cover"
              :alt="anime.name"
              loading="lazy"
              @error="hideBrokenImage"
            /><span class="recommendation-index">0{{ index + 1 }}</span></span
          >
          <span class="recommendation-info"
            ><small>{{ anime.theme }}</small
            ><strong>{{ anime.name }}</strong
            ><span
              ><AppIcon name="pin" :size="11" />{{ anime.location }}</span
            ></span
          >
          <span class="recommendation-arrow"
            ><AppIcon name="arrow" :size="16"
          /></span>
        </button>
      </section>
      <div class="journey-note">
        <span class="note-icon"><AppIcon name="bookmark" :size="18" /></span>
        <div>
          <strong>先收藏心动，再决定出发</strong>
          <p>跨作品收藏地标，让 AI 为你串起旅程。</p>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import AppIcon from './AppIcon.vue'
import { recommendations } from '../utils/recommendations'
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
    // The store exposes a readable error beside the search field.
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
  ElMessage.success(`已收藏 ${savedCount.value - previous} 个场景坐标`)
}
function hideBrokenImage(event) {
  event.target.style.visibility = 'hidden'
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
  padding: 6px 0 2px;
}
.search-intro {
  position: relative;
  padding: 2px 0 25px;
}
.search-intro .eyebrow {
  font-size: 9px;
  letter-spacing: 1.7px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tiny-line {
  width: 17px;
  height: 1px;
  background: #899677;
}
.search-intro h1 {
  font-size: clamp(30px, 2.4vw, 38px);
  line-height: 1.5;
  font-weight: 650;
  letter-spacing: 2px;
  margin: 20px 0 11px;
}
.title-dot {
  color: var(--accent-color);
}
.search-intro > p {
  font-size: 12px;
  line-height: 1.9;
  color: var(--text-secondary);
}
.intro-stamp {
  position: absolute;
  right: 8px;
  top: 68px;
  color: #a98c6a;
  font-family: 'KaiTi', 'STKaiti', serif;
  font-size: 29px;
  border: 1px solid #a98c6a70;
  border-radius: 50%;
  width: 53px;
  height: 61px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transform: rotate(12deg);
  opacity: 0.7;
}
.intro-stamp small {
  font-family: serif;
  font-size: 8px;
  letter-spacing: 3px;
}
.search-form {
  margin-bottom: 28px;
}
.search-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 11px;
}
.search-field {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 5px 6px 5px 13px;
  border: 1px solid #d5ddce;
  border-radius: 11px;
  background: var(--surface-color);
  color: #8b9580;
  transition: box-shadow 0.2s;
}
.search-field:focus-within {
  border-color: #779071;
  box-shadow: 0 0 0 3px #65845410;
}
.search-field > svg {
  flex-shrink: 0;
}
.search-field input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  font-size: 12px;
  outline: 0;
  color: var(--text-color);
}
.search-field input::placeholder {
  color: #919988;
}
.search-field button {
  border: 0;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  background: var(--primary-color);
  color: #fff;
  cursor: pointer;
}
.search-field button:disabled {
  background: #e9ede3;
  color: #9ea894;
  cursor: default;
}
.search-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 9px;
  font-size: 9px;
  color: #8f9687;
}
.search-hint kbd {
  padding: 0 4px;
  border: 1px solid #dfe2d7;
  border-radius: 3px;
  font-size: 10px;
}
.search-error {
  margin: -10px 0 20px;
}
.search-error :deep(.el-alert) {
  font-size: 11px;
  padding: 10px;
}
.search-error > p {
  font-size: 10px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin-top: 9px;
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 13px;
}
.section-heading h2 {
  font-size: 13px;
  font-weight: 650;
}
.section-heading h2 > span {
  color: var(--text-secondary);
  font-size: 11px;
  margin-left: 4px;
}
.section-caption {
  color: #939b89;
  letter-spacing: 1.4px;
  font-size: 8px;
}
.recommendation-card {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 9px;
  margin-bottom: 10px;
  border: 1px solid #e4e6dc;
  background: #fcfcf6;
  border-radius: 12px;
  text-align: left;
  cursor: pointer;
  color: var(--text-color);
  transition:
    transform 0.2s,
    border-color 0.2s,
    background 0.2s;
}
.recommendation-card:hover:not(:disabled) {
  transform: translateX(3px);
  border-color: #aeba9e;
  background: #fffef9;
}
.recommendation-card:disabled {
  opacity: 0.55;
}
.recommendation-cover {
  position: relative;
  width: 64px;
  height: 80px;
  border-radius: 7px;
  flex-shrink: 0;
  overflow: hidden;
  background: #e0e6d6;
}
.peach .recommendation-cover {
  background: #f0e2d4;
}
.blue .recommendation-cover {
  background: #dce7e9;
}
.recommendation-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.recommendation-index {
  position: absolute;
  bottom: 5px;
  left: 5px;
  color: #fff;
  font-family: Georgia, serif;
  font-size: 12px;
  background: #233d3a90;
  padding: 2px 4px;
  border-radius: 3px;
}
.recommendation-info {
  flex: 1;
  min-width: 0;
}
.recommendation-info > small {
  display: block;
  color: #949a86;
  font-size: 9px;
  margin-bottom: 7px;
  letter-spacing: 1px;
}
.recommendation-info > strong {
  font-size: 13px;
  display: block;
  line-height: 1.45;
  font-weight: 650;
}
.recommendation-info > span {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  margin-top: 8px;
  color: var(--text-secondary);
}
.recommendation-arrow {
  display: flex;
  color: #8c9b80;
  margin-right: 3px;
}
.journey-note {
  display: flex;
  gap: 10px;
  padding: 16px 0 8px;
  align-items: flex-start;
}
.note-icon {
  color: #98a588;
  padding-top: 2px;
}
.journey-note strong {
  font-size: 11px;
  font-weight: 500;
  color: #78866d;
}
.journey-note p {
  font-size: 10px;
  color: #929a89;
  margin-top: 5px;
  line-height: 1.7;
}
.result-item {
  border: 0;
  border-bottom: 1px solid var(--border-color);
  background: none;
  width: 100%;
  padding: 12px 3px;
  display: flex;
  text-align: left;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  color: var(--text-secondary);
}
.result-item:hover {
  background: var(--primary-soft);
}
.result-cover {
  display: grid;
  place-items: center;
  width: 43px;
  height: 58px;
  background: var(--primary-soft);
  border-radius: 5px;
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
}
.result-info strong {
  display: block;
  font-size: 12px;
  color: var(--text-color);
  line-height: 1.5;
}
.result-info small {
  display: block;
  font-size: 10px;
  margin-top: 3px;
}
.result-info > span {
  display: block;
  font-size: 9px;
  margin-top: 6px;
}
.result-info i {
  font-style: normal;
  padding: 0 5px;
}
.no-results {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.8;
  background: var(--primary-soft);
  border-radius: 10px;
  padding: 18px;
  margin-bottom: 20px;
}
.loading-note {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--primary-color);
  font-size: 12px;
  padding: 14px 0;
}
.small-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid #a7b697;
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
.current-anime {
  margin-top: 20px;
}
.anime-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px;
  background: #ecefe3;
  border: 1px solid #e0e5d6;
  border-radius: 12px;
}
.anime-cover {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 60px;
  height: 86px;
  overflow: hidden;
  border-radius: 6px;
  background: #d9e0cc;
}
.anime-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.anime-details {
  min-width: 0;
}
.anime-details .eyebrow {
  font-size: 7px;
  letter-spacing: 1.4px;
}
.anime-details h2 {
  font-size: 15px;
  margin: 8px 0 5px;
  line-height: 1.5;
}
.anime-details p {
  font-size: 10px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.anime-city {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #738166;
  font-size: 10px;
  margin-top: 8px;
}
.anime-stats {
  display: flex;
  justify-content: space-around;
  padding: 16px 0;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 10px;
}
.anime-stats > span + span {
  border-left: 1px solid var(--border-color);
  padding-left: 20px;
}
.anime-stats strong {
  font-size: 19px;
  font-weight: 550;
  color: var(--primary-color);
  margin-right: 4px;
}
.scenes-section .section-heading {
  margin-bottom: 6px;
}
.scene-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 5px 4px 0;
  border-bottom: 1px solid #e4e7dc;
  border-radius: 6px;
}
.scene-row.selected {
  background: #e9eee1;
}
.scene-select {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  text-align: left;
  gap: 11px;
  padding: 10px 5px;
  border: 0;
  background: none;
  color: var(--text-color);
  cursor: pointer;
}
.scene-number {
  color: #9ba68f;
  font-family: Georgia, serif;
  font-size: 16px;
  width: 22px;
  flex-shrink: 0;
}
.scene-name {
  min-width: 0;
}
.scene-name strong {
  display: block;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scene-name small {
  display: block;
  font-size: 9px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.scene-save {
  width: 27px;
  height: 27px;
  border: 1px solid #dce2d3;
  border-radius: 7px;
  flex-shrink: 0;
}
.scene-save.saved {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}
@media (max-height: 800px) and (min-width: 821px) {
  .search-intro {
    padding-bottom: 20px;
  }
  .search-intro h1 {
    font-size: 30px;
    margin-top: 14px;
  }
  .search-form {
    margin-bottom: 22px;
  }
  .recommendation-cover {
    width: 51px;
    height: 64px;
  }
  .recommendation-card {
    padding: 8px;
    margin-bottom: 8px;
    gap: 10px;
  }
  .recommendation-info > small {
    margin-bottom: 4px;
  }
  .recommendation-info > span {
    margin-top: 5px;
  }
  .journey-note {
    padding-top: 12px;
  }
}
@media (max-width: 820px) {
  .search-intro h1 {
    font-size: 34px;
  }
  .search-intro {
    padding-bottom: 22px;
  }
  .search-intro > p br {
    display: none;
  }
  .intro-stamp {
    right: 20px;
    top: 55px;
  }
  .recommendation-cover {
    width: 64px;
    height: 76px;
  }
  .search-form {
    margin-bottom: 26px;
  }
}
</style>
