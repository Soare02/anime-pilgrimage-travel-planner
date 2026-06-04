<template>
  <div class="app-layout">
    <!-- 主地图与侧边栏视图 -->
    <template v-if="!store.showAdminPage">
      <aside class="sidebar">
        <div class="sidebar-content">
          <SearchPanel />
          <CoordinateLibrary />
        </div>
      </aside>
      <main class="main-content">
        <MapView />
        <LandmarkDock />
      </main>
    </template>

    <!-- 全屏 RAG 管理后台 -->
    <template v-else>
      <RagAdminPanel />
    </template>
  </div>
</template>

<script setup>
import SearchPanel from './components/SearchPanel.vue'
import CoordinateLibrary from './components/CoordinateLibrary.vue'
import MapView from './components/MapView.vue'
import LandmarkDock from './components/LandmarkDock.vue'
import RagAdminPanel from './components/RagAdminPanel.vue'
import { useAppStore } from './stores/app'

const store = useAppStore()
</script>

<style scoped>
.app-layout {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  position: absolute;
  left: 20px;
  top: 20px;
  bottom: 20px;
  z-index: 1000;
  width: 360px;
  background-color: var(--sidebar-bg);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 16px;
  box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.main-content {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  z-index: 1;
}
</style>
