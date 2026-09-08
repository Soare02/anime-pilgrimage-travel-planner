<template>
  <div class="app-layout">
    <div v-show="!store.showAdminPage" class="travel-shell">
      <header class="app-header">
        <button
          class="brand"
          aria-label="巡礼手帖，返回探索"
          @click="navigate('explore')"
        >
          <span class="brand-symbol"
            ><AppIcon name="compass" :size="29"
          /></span>
          <span class="brand-type"
            ><strong>巡礼手帖<span class="brand-period">.</span></strong
            ><span>ANIME ATLAS</span></span
          >
        </button>
        <nav class="main-nav" aria-label="主导航">
          <button
            v-for="item in navigation"
            :key="item.key"
            :class="{ active: store.activePanel === item.key }"
            :aria-current="store.activePanel === item.key ? 'page' : undefined"
            @click="navigate(item.key)"
          >
            <AppIcon :name="item.icon" :size="17" /><span>{{
              item.label
            }}</span>
            <span
              v-if="item.key === 'library' && store.coordinateLibrary.length"
              class="nav-count"
              >{{ store.coordinateLibrary.length }}</span
            >
          </button>
        </nav>
        <div class="header-actions">
          <button
            class="icon-button admin-link"
            title="数据中心"
            aria-label="打开数据中心"
            @click="store.showAdminPage = true"
          >
            <AppIcon name="grid" :size="18" />
          </button>
          <span class="header-divider"></span>
          <button class="settings-button" @click="store.settingsOpen = true">
            <AppIcon name="sparkles" :size="17" /><span>AI 旅伴</span
            ><AppIcon name="settings" :size="15" />
          </button>
        </div>
      </header>

      <div class="mobile-switch" aria-label="视图切换">
        <button
          :class="{ active: !mobileMapVisible }"
          :aria-pressed="!mobileMapVisible"
          @click="mobileMapVisible = false"
        >
          <AppIcon name="bookmark" :size="16" />{{
            store.activePanel === 'explore'
              ? '作品探索'
              : store.activePanel === 'library'
                ? '收藏规划'
                : '旅途档案'
          }}
        </button>
        <button
          :class="{ active: mobileMapVisible }"
          :aria-pressed="mobileMapVisible"
          @click="mobileMapVisible = true"
        >
          <AppIcon name="map" :size="16" />巡礼地图
        </button>
      </div>

      <div class="workspace" :class="{ 'show-mobile-map': mobileMapVisible }">
        <aside class="sidebar" aria-label="巡礼工作台">
          <div
            v-show="store.activePanel === 'explore'"
            class="explore-scroll scrollbar-wrapper"
          >
            <SearchPanel @show-map="mobileMapVisible = true" />
          </div>
          <div v-show="store.activePanel !== 'explore'" class="library-pane">
            <CoordinateLibrary
              @explore="navigate('explore')"
              @show-map="mobileMapVisible = true"
            />
          </div>
          <div class="sidebar-footer">
            <button
              v-if="
                store.coordinateLibrary.length &&
                store.activePanel === 'explore'
              "
              class="collection-link"
              @click="navigate('library')"
            >
              <span class="collection-icon"
                ><AppIcon name="bookmark" :size="18"
              /></span>
              <span
                ><strong
                  >{{
                    store.coordinateLibrary.length
                  }}
                  处心动，已收入手帖</strong
                ><small>去安排我的巡礼路线</small></span
              >
              <AppIcon name="arrow" :size="18" />
            </button>
            <div v-else class="field-note">
              <AppIcon name="sun" :size="18" /><span
                >把屏幕里的心动，变成脚下的风景。</span
              >
            </div>
          </div>
        </aside>

        <main class="main-content" aria-label="圣地巡礼地图">
          <div class="workspace-heading">
            <div>
              <span class="eyebrow">THE WORLD BEHIND THE SCENES</span>
              <h2>{{ mapHeading }}</h2>
            </div>
            <span class="map-status"><span></span>巡礼地图</span>
          </div>
          <div class="map-frame"><MapView /></div>
          <LandmarkDock />
        </main>
      </div>

      <footer class="app-footer">
        <span>每一帧喜欢，都值得亲自抵达。</span
        ><span
          >场景数据
          <a href="https://anitabi.cn" target="_blank" rel="noopener noreferrer"
            >Anitabi</a
          ><i>×</i>作品信息
          <a href="https://bgm.tv" target="_blank" rel="noopener noreferrer"
            >Bangumi</a
          ></span
        >
      </footer>
    </div>
    <RagAdminPanel v-if="store.showAdminPage" />
    <AiSettingsDialog />
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, ref } from 'vue'
import SearchPanel from './components/SearchPanel.vue'
import CoordinateLibrary from './components/CoordinateLibrary.vue'
import MapView from './components/MapView.vue'
import LandmarkDock from './components/LandmarkDock.vue'
import AppIcon from './components/AppIcon.vue'
import AiSettingsDialog from './components/AiSettingsDialog.vue'
import { useAppStore } from './stores/app'

const RagAdminPanel = defineAsyncComponent(
  () => import('./components/RagAdminPanel.vue')
)
const store = useAppStore()
const mobileMapVisible = ref(false)
const navigation = [
  { key: 'explore', label: '发现圣地', icon: 'compass' },
  { key: 'library', label: '我的巡礼', icon: 'bookmark' },
  { key: 'history', label: '旅途档案', icon: 'clock' }
]
const mapHeading = computed(() =>
  store.activePanel === 'library' && store.coordinateLibrary.length
    ? '让心动的坐标，连成一段旅程'
    : store.bangumi
      ? store.bangumi.cn || store.bangumi.title
      : '故事里的风景，就在这里'
)
function navigate(panel) {
  store.activePanel = panel
  mobileMapVisible.value = false
}
</script>

<style scoped>
.app-layout,
.travel-shell {
  width: 100%;
  height: 100%;
  min-height: 0;
}
.travel-shell {
  display: flex;
  flex-direction: column;
}
.app-header {
  height: 88px;
  flex-shrink: 0;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  border: 0;
  padding: 0;
  background: transparent;
  text-align: left;
  color: var(--text-color);
  cursor: pointer;
}
.brand-symbol {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  background: var(--primary-color);
  color: #f8f5e9;
  border-radius: 14px 14px 14px 4px;
  transform: rotate(-5deg);
}
.brand-symbol svg {
  transform: rotate(5deg);
}
.brand-type {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.brand-type strong {
  font-size: 23px;
  letter-spacing: 2px;
  font-weight: 750;
  line-height: 1.1;
}
.brand-period {
  color: var(--accent-color);
}
.brand-type > span {
  font-size: 9px;
  letter-spacing: 3.5px;
  color: var(--text-secondary);
}
.main-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px;
  background: #eeeee7;
  border-radius: 12px;
}
.main-nav button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 19px;
  color: var(--text-secondary);
  background: transparent;
  border: 0;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
  transition:
    background 0.2s,
    color 0.2s;
}
.main-nav button.active {
  background: var(--surface-color);
  color: var(--primary-color);
  box-shadow: 0 2px 6px #20382a09;
  font-weight: 650;
}
.main-nav button:hover {
  color: var(--primary-color);
}
.nav-count {
  border-radius: 5px;
  background: var(--primary-soft);
  padding: 1px 5px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 13px;
}
.header-divider {
  width: 1px;
  height: 20px;
  background: var(--border-color);
}
.settings-button {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid #d8dfd4;
  background: transparent;
  padding: 11px 15px;
  border-radius: 9px;
  color: var(--primary-color);
  font-size: 12px;
  cursor: pointer;
}
.settings-button:hover {
  background: var(--primary-soft);
}
.workspace {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 28px;
  flex: 1;
  min-height: 0;
  padding: 8px 32px 0;
}
.sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border-right: 1px solid var(--border-color);
  padding-right: 26px;
}
.explore-scroll {
  flex: 1;
  min-height: 0;
  padding-right: 3px;
}
.library-pane {
  display: flex;
  flex: 1;
  min-height: 0;
}
.sidebar-footer {
  flex-shrink: 0;
  margin-top: 16px;
  padding-top: 17px;
  border-top: 1px dashed #d9dbd0;
}
.field-note {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #818574;
  font-size: 11px;
  padding: 4px 0;
}
.collection-link {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 13px;
  border: 1px solid #dce2d2;
  border-radius: 12px;
  background: #ecefe2;
  color: var(--primary-color);
  cursor: pointer;
  text-align: left;
}
.collection-link > span:nth-child(2) {
  flex: 1;
}
.collection-link strong,
.collection-link small {
  display: block;
}
.collection-link strong {
  font-size: 12px;
  font-weight: 600;
}
.collection-link small {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-secondary);
}
.collection-icon {
  padding: 9px;
  border-radius: 9px;
  background: #fcfcf6;
  display: flex;
}
.main-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  min-width: 0;
}
.workspace-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  gap: 16px;
  padding-bottom: 2px;
}
.workspace-heading .eyebrow {
  font-size: 9px;
  letter-spacing: 2.2px;
}
.workspace-heading h2 {
  font-size: 20px;
  font-weight: 600;
  margin-top: 7px;
  letter-spacing: 0.5px;
}
.map-status {
  display: flex;
  gap: 7px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 10px;
  white-space: nowrap;
}
.map-status > span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #648567;
  box-shadow: 0 0 0 4px #64856710;
}
.map-frame {
  flex: 1;
  min-height: 180px;
  border: 1px solid #d5dccf;
  border-radius: 20px;
  overflow: hidden;
  position: relative;
  background: #e7ecdf;
}
.app-footer {
  height: 37px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 33px;
  flex-shrink: 0;
  font-size: 9px;
  letter-spacing: 0.6px;
  color: #888d80;
}
.app-footer a {
  color: inherit;
  text-decoration: none;
}
.app-footer a:hover {
  color: var(--primary-color);
}
.app-footer i {
  font-style: normal;
  padding: 0 8px;
  opacity: 0.5;
}
.mobile-switch {
  display: none;
}
@media (min-width: 1600px) {
  .workspace {
    grid-template-columns: 380px minmax(0, 1fr);
    gap: 32px;
  }
  .sidebar {
    padding-right: 30px;
  }
  .app-header {
    height: 96px;
  }
}
@media (max-width: 1100px) {
  .app-header {
    padding: 0 22px;
    gap: 15px;
  }
  .workspace {
    grid-template-columns: 300px minmax(0, 1fr);
    padding: 5px 22px 0;
    gap: 20px;
  }
  .sidebar {
    padding-right: 20px;
  }
  .main-nav button {
    padding: 10px 12px;
  }
  .brand-type strong {
    font-size: 20px;
  }
  .header-actions {
    gap: 8px;
  }
  .admin-link,
  .header-divider {
    display: none;
  }
  .workspace-heading h2 {
    font-size: 17px;
  }
}
@media (max-width: 820px) {
  .app-header {
    height: auto;
    padding: 18px 20px 12px;
    flex-wrap: wrap;
    gap: 18px;
  }
  .brand-symbol {
    width: 37px;
    height: 37px;
    border-radius: 11px 11px 11px 3px;
  }
  .brand-type strong {
    font-size: 20px;
  }
  .brand-type > span {
    font-size: 8px;
    letter-spacing: 2.8px;
  }
  .main-nav {
    order: 3;
    width: 100%;
    padding: 4px;
  }
  .main-nav button {
    flex: 1;
    padding: 11px 6px;
    gap: 6px;
    font-size: 12px;
  }
  .header-actions {
    margin-left: auto;
  }
  .settings-button {
    padding: 9px 11px;
    gap: 6px;
  }
  .settings-button svg:last-child {
    display: none;
  }
  .admin-link {
    display: inline-flex;
  }
  .mobile-switch {
    display: flex;
    justify-content: center;
    gap: 25px;
    margin: 0 20px 12px;
    border-bottom: 1px solid var(--border-color);
  }
  .mobile-switch button {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 9px 4px 12px;
    color: var(--text-secondary);
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    cursor: pointer;
  }
  .mobile-switch button.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
  }
  .workspace {
    display: flex;
    padding: 0 20px;
    gap: 0;
  }
  .sidebar {
    width: 100%;
    border: 0;
    padding: 0;
  }
  .sidebar-footer {
    margin-top: 12px;
    padding-top: 12px;
  }
  .main-content {
    display: none;
    width: 100%;
    gap: 12px;
  }
  .show-mobile-map .sidebar {
    display: none;
  }
  .show-mobile-map .main-content {
    display: flex;
  }
  .workspace-heading {
    display: none;
  }
  .app-footer {
    height: 32px;
    padding: 0 20px;
    justify-content: center;
    font-size: 8px;
  }
  .app-footer > span:first-child {
    display: none;
  }
  .map-frame {
    border-radius: 15px;
    min-height: 160px;
  }
}
@media (prefers-reduced-motion: reduce) {
  * {
    transition: none !important;
  }
}
</style>
