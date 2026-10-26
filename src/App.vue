<template>
  <div class="app-layout">
    <div v-show="!store.showAdminPage" class="travel-shell">
      <header class="app-header">
        <button
          class="brand"
          aria-label="巡礼手帖，返回探索"
          @click="navigate('explore')"
        >
          <span class="brand-symbol">
            <AppIcon name="compass" :size="22" />
          </span>
          <strong class="brand-title">巡礼手帖</strong>
        </button>

        <nav class="main-nav" aria-label="主导航">
          <button
            v-for="item in navigation"
            :key="item.key"
            :class="{ active: store.activePanel === item.key }"
            :aria-current="store.activePanel === item.key ? 'page' : undefined"
            @click="navigate(item.key)"
          >
            <AppIcon :name="item.icon" :size="17" />
            <span>{{ item.label }}</span>
            <span
              v-if="item.key === 'library' && store.coordinateLibrary.length"
              class="nav-count"
            >
              {{ store.coordinateLibrary.length }}
            </span>
          </button>
        </nav>

        <div class="header-actions">
          <button
            class="glass-action-btn admin-link"
            title="数据中心"
            aria-label="打开数据中心"
            @click="store.showAdminPage = true"
          >
            <AppIcon name="grid" :size="17" />
            <span>数据中心</span>
          </button>
          <button class="glass-action-btn settings-button" @click="store.settingsOpen = true">
            <AppIcon name="sparkles" :size="17" />
            <span>AI 设置</span>
          </button>
        </div>
      </header>

      <div class="mobile-switch" aria-label="视图切换">
        <button
          :class="{ active: !mobileMapVisible }"
          :aria-pressed="!mobileMapVisible"
          @click="mobileMapVisible = false"
        >
          <AppIcon name="bookmark" :size="16" />
          {{
            store.activePanel === 'explore'
              ? '作品探索'
              : store.activePanel === 'library'
                ? '我的巡礼'
                : '旅途档案'
          }}
        </button>
        <button
          :class="{ active: mobileMapVisible }"
          :aria-pressed="mobileMapVisible"
          @click="mobileMapVisible = true"
        >
          <AppIcon name="map" :size="16" />
          巡礼地图
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

          <div v-if="store.activePanel === 'explore'" class="sidebar-footer">
            <button
              v-if="store.coordinateLibrary.length"
              class="collection-link"
              @click="navigate('library')"
            >
              <span class="collection-icon">
                <AppIcon name="bookmark" :size="18" />
              </span>
              <span class="collection-body">
                <strong>已收藏 {{ store.coordinateLibrary.length }} 个取景地标</strong>
                <span>前往我的巡礼，生成多日行程路线</span>
              </span>
              <AppIcon name="arrow" :size="17" />
            </button>
            <div v-else class="workflow-bar">
              <div class="workflow-step">
                <span class="step-badge">1</span>
                <span>搜索作品</span>
              </div>
              <span class="workflow-sep"></span>
              <div class="workflow-step">
                <span class="step-badge">2</span>
                <span>收藏坐标</span>
              </div>
              <span class="workflow-sep"></span>
              <div class="workflow-step">
                <span class="step-badge">3</span>
                <span>AI 排线</span>
              </div>
            </div>
          </div>
        </aside>

        <main class="main-content" aria-label="圣地巡礼地图">
          <div class="map-frame">
            <MapView />
          </div>
          <LandmarkDock />
        </main>
      </div>
    </div>
    <section
      v-if="store.showAdminPage && !adminPanel"
      class="admin-load-panel"
      aria-label="数据中心加载"
    >
      <h1>巡礼数据中心</h1>
      <p :role="adminLoadError ? 'alert' : 'status'">
        {{ adminLoadError ? '数据中心页面加载失败，请重试。' : '正在加载数据中心…' }}
      </p>
      <div class="admin-load-actions">
        <button v-if="adminLoadError" class="primary-button" @click="loadAdminPanel">重试</button>
        <button class="glass-action-btn" @click="store.showAdminPage = false">返回巡礼地图</button>
      </div>
    </section>
    <component :is="adminPanel" v-if="store.showAdminPage && adminPanel" />
    <AiSettingsDialog />
  </div>
</template>

<script setup>
import { ref, shallowRef, watch } from 'vue'
import SearchPanel from './components/SearchPanel.vue'
import CoordinateLibrary from './components/CoordinateLibrary.vue'
import MapView from './components/MapView.vue'
import LandmarkDock from './components/LandmarkDock.vue'
import AppIcon from './components/AppIcon.vue'
import AiSettingsDialog from './components/AiSettingsDialog.vue'
import { useAppStore } from './stores/app'

const store = useAppStore()
const adminPanel = shallowRef(null)
const adminLoadError = ref(false)
let adminLoading = false

async function loadAdminPanel() {
  if (adminPanel.value || adminLoading) return
  adminLoading = true
  adminLoadError.value = false
  let timeout
  try {
    const module = await Promise.race([
      import('./components/RagAdminPanel.vue'),
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('数据中心加载超时')), 20000)
      })
    ])
    adminPanel.value = module.default
  } catch (error) {
    adminLoadError.value = true
    console.error('数据中心页面加载失败:', error)
  } finally {
    clearTimeout(timeout)
    adminLoading = false
  }
}

watch(() => store.showAdminPage, (show) => {
  if (show) loadAdminPanel()
}, { immediate: true })

const mobileMapVisible = ref(false)
const navigation = [
  { key: 'explore', label: '发现圣地', icon: 'compass' },
  { key: 'library', label: '我的巡礼', icon: 'bookmark' },
  { key: 'history', label: '旅途档案', icon: 'clock' }
]

function navigate(panel) {
  store.activePanel = panel
  mobileMapVisible.value = false
}
</script>

<style>
.admin-load-panel {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 24px;
  color: var(--text-color);
  text-align: center;
}

.admin-load-panel h1 {
  font-size: 22px;
}

.admin-load-panel p {
  color: var(--text-secondary);
}

.admin-load-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
}

:root {
  color-scheme: light;
  --bg-color: #eef2f6 !important;
  --surface-color: rgba(255, 255, 255, 0.78) !important;
  --surface-solid: #ffffff !important;
  --sidebar-bg: rgba(255, 255, 255, 0.72) !important;
  --card-bg: rgba(255, 255, 255, 0.68) !important;
  --glass-bg: rgba(255, 255, 255, 0.72) !important;
  --glass-bg-strong: rgba(255, 255, 255, 0.88) !important;
  --glass-bg-subtle: rgba(255, 255, 255, 0.52) !important;
  --glass-border: rgba(255, 255, 255, 0.85) !important;
  --glass-blur: blur(20px) saturate(180%) !important;
  --glass-shadow: 0 10px 32px rgba(15, 23, 42, 0.06) !important;
  --glass-shadow-sm: 0 2px 12px rgba(15, 23, 42, 0.04) !important;
  --primary-color: #2563eb !important;
  --primary-hover: #1d4ed8 !important;
  --primary-soft: rgba(37, 99, 235, 0.08) !important;
  --accent-color: #3b82f6 !important;
  --text-color: #0f172a !important;
  --text-secondary: #64748b !important;
  --text-muted: #94a3b8 !important;
  --border-color: rgba(15, 23, 42, 0.08) !important;
  --el-color-primary: #2563eb !important;
}

body {
  color: var(--text-color) !important;
  background:
    radial-gradient(circle at 10% 15%, rgba(191, 219, 254, 0.55), transparent 40%),
    radial-gradient(circle at 90% 85%, rgba(224, 231, 255, 0.6), transparent 42%),
    linear-gradient(135deg, #f8fafc 0%, #eef2f6 100%) !important;
}
</style>

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
  padding: 16px 20px 20px;
  gap: 16px;
}

.app-header {
  height: 64px;
  flex-shrink: 0;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  background: rgba(255, 255, 255, 0.74);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 18px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.05);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--text-color);
  cursor: pointer;
}

.brand-symbol {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  border-radius: 11px;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
}

.brand-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.main-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  background: rgba(15, 23, 42, 0.04);
  border-radius: 12px;
}

.main-nav button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 18px;
  color: var(--text-secondary);
  background: transparent;
  border: 0;
  border-radius: 9px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  transition: all 0.18s ease;
}

.main-nav button.active {
  background: rgba(255, 255, 255, 0.94);
  color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
  font-weight: 600;
}

.main-nav button:hover:not(.active) {
  color: var(--text-color);
}

.nav-count {
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-color);
  padding: 1px 7px;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.glass-action-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.7);
  padding: 8px 14px;
  border-radius: 10px;
  color: var(--text-color);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s ease;
}

.glass-action-btn:hover {
  background: #ffffff;
  color: var(--primary-color);
  border-color: rgba(37, 99, 235, 0.25);
}

.workspace {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 20px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(22px) saturate(180%);
  -webkit-backdrop-filter: blur(22px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 20px;
  box-shadow:
    0 10px 32px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.explore-scroll {
  flex: 1;
  min-height: 0;
  padding-right: 4px;
}

.library-pane {
  display: flex;
  flex: 1;
  min-height: 0;
}

.sidebar-footer {
  flex-shrink: 0;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
}

.collection-link {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 14px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--primary-color);
  cursor: pointer;
  text-align: left;
  transition: all 0.18s ease;
}

.collection-link:hover {
  background: rgba(37, 99, 235, 0.13);
  transform: translateY(-1px);
}

.collection-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  flex-shrink: 0;
}

.collection-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.collection-body strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}

.collection-body span {
  font-size: 12px;
  color: var(--text-secondary);
}

.workflow-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--border-color);
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.step-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 600;
}

.workflow-sep {
  width: 16px;
  height: 1px;
  background: var(--border-color);
}

.main-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

.map-frame {
  flex: 1;
  min-height: 200px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 20px;
  overflow: hidden;
  position: relative;
  background: #e2e8f0;
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.06);
}

.mobile-switch {
  display: none;
}

@media (min-width: 1600px) {
  .workspace {
    grid-template-columns: 410px minmax(0, 1fr);
    gap: 20px;
  }
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 330px minmax(0, 1fr);
  }
  .admin-link span {
    display: none;
  }
  .admin-link {
    padding: 8px 10px;
  }
}

@media (max-width: 820px) {
  .travel-shell {
    padding: 12px;
    gap: 12px;
  }
  .app-header {
    height: auto;
    padding: 12px 14px;
    flex-wrap: wrap;
    gap: 12px;
    border-radius: 16px;
  }
  .main-nav {
    order: 3;
    width: 100%;
  }
  .main-nav button {
    flex: 1;
    padding: 8px 6px;
    font-size: 13px;
  }
  .header-actions {
    margin-left: auto;
  }
  .mobile-switch {
    display: flex;
    gap: 8px;
    padding: 4px;
    background: rgba(255, 255, 255, 0.74);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.85);
    border-radius: 12px;
  }
  .mobile-switch button {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 12px;
    color: var(--text-secondary);
    background: transparent;
    border: 0;
    border-radius: 9px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
  }
  .mobile-switch button.active {
    background: rgba(255, 255, 255, 0.94);
    color: var(--primary-color);
    font-weight: 600;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05);
  }
  .workspace {
    display: flex;
    gap: 0;
  }
  .sidebar {
    width: 100%;
    padding: 16px;
    border-radius: 16px;
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
  .map-frame {
    border-radius: 16px;
  }
}
</style>
