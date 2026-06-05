import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchBangumiLite, fetchBangumiPointsDetail, searchBangumiByKey, generateAIRoute } from '../utils/api'
import { planRoute } from '../utils/routePlanner'

export const useAppStore = defineStore('app', () => {
  const bangumi = ref(null)
  const points = ref([])
  const selectedPointId = ref(null)
  const itinerary = ref([])
  const days = ref(1)
  const loading = ref(false)
  const error = ref(null)
  const searchResults = ref([])
  const searching = ref(false)

  const coordinateLibrary = ref([])
  const libraryItinerary = ref([])
  const libraryDays = ref(1)
  const libraryAiResponse = ref('')
  const generatedLandmarks = ref([])  // L2: 生成时的地标快照，展开视图用
  const routeHistory = ref(loadRouteHistory())
  const compareData = ref(null)
  const showAdminPage = ref(false)
  const aiConfig = ref(loadAiConfig())

  function loadAiConfig() {
    const defaultConfig = {
      scheme: 'cloud',
      cloud: {
        url: '/ark/bots/chat/completions',
        apiKey: '',
        model: ''
      },
      local: {
        url: 'http://localhost:11434/v1/chat/completions',
        apiKey: '',
        model: 'deepseek-r1:7b'
      },
      agent: {
        url: '/api/agent/plan',
        apiKey: '',
        model: ''
      }
    }
    try {
      const saved = localStorage.getItem('ai-config')
      if (saved) {
        const parsed = JSON.parse(saved)
        return {
          ...defaultConfig,
          ...parsed,
          cloud: { ...defaultConfig.cloud, ...(parsed.cloud || {}) },
          local: { ...defaultConfig.local, ...(parsed.local || {}) },
          agent: { ...defaultConfig.agent, ...(parsed.agent || {}) }
        }
      }
    } catch {}
    return defaultConfig
  }

  function persistAiConfig() {
    try {
      localStorage.setItem('ai-config', JSON.stringify(aiConfig.value))
    } catch {}
  }

  function updateAiConfig(scheme, field, value) {
    if (scheme === 'scheme') {
      aiConfig.value.scheme = value
    } else if (aiConfig.value[scheme] !== undefined) {
      aiConfig.value[scheme][field] = value
    }
    persistAiConfig()
  }

  const activeAiConfig = computed(() => aiConfig.value[aiConfig.value.scheme] || aiConfig.value.cloud)

  function saveAiConfig() {
    persistAiConfig()
  }

  function loadRouteHistory() {
    try {
      const saved = localStorage.getItem('route-history')
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  }

  function persistRouteHistory() {
    try {
      localStorage.setItem('route-history', JSON.stringify(routeHistory.value))
    } catch (e) {
      console.warn('Failed to save route history:', e)
    }
  }

  function saveRouteHistory(landmarks, aiResponse, days, scheme) {
    routeHistory.value.push({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      timestamp: Date.now(),
      days,
      landmarks: landmarks.map(lm => ({ id: lm.id, bangumiId: lm.bangumiId })),
      aiResponse,
      scheme
    })
    persistRouteHistory()
  }

  function deleteRouteHistory(id) {
    routeHistory.value = routeHistory.value.filter(h => h.id !== id)
    persistRouteHistory()
  }

  function clearRouteHistory() {
    routeHistory.value = []
    persistRouteHistory()
  }

  const selectedPoint = computed(() => {
    return points.value.find(p => p.id === selectedPointId.value) || null
  })

  const checkedPoints = computed(() => {
    return points.value.filter(p => p.checked)
  })

  const checkedCount = computed(() => checkedPoints.value.length)

  const allChecked = computed(() => {
    return points.value.length > 0 && points.value.every(p => p.checked)
  })

  const someChecked = computed(() => {
    return checkedPoints.value.length > 0 && !allChecked.value
  })

  const librarySelected = computed(() => {
    return coordinateLibrary.value.filter(e => e.checked)
  })

  const defaultCenter = computed(() => {
    if (bangumi.value && bangumi.value.geo) {
      return bangumi.value.geo
    }
    return [35.6895, 139.6917]
  })

  const defaultZoom = computed(() => {
    if (bangumi.value && bangumi.value.zoom) {
      return bangumi.value.zoom
    }
    return 10
  })

  async function searchBangumi(subjectID) {
    loading.value = true
    error.value = null
    bangumi.value = null
    points.value = []
    itinerary.value = []
    selectedPointId.value = null

    try {
      const liteData = await fetchBangumiLite(subjectID)
      bangumi.value = liteData

      const detailData = await fetchBangumiPointsDetail(subjectID, true)
      points.value = detailData.map(p => ({
        id: p.id,
        name: p.cn || p.name,
        originalName: p.name,
        image: p.image || '',
        ep: p.ep,
        s: p.s,
        geo: p.geo,
        origin: p.origin || '',
        originURL: p.originURL || '',
        day: null,
        checked: true
      }))
    } catch (e) {
      error.value = e.message || '获取数据失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function generateItinerary() {
    const selected = checkedPoints.value
    if (selected.length === 0) return

    loading.value = true
    try {
      const result = planRoute(selected, days.value, defaultCenter.value)
      
      points.value.forEach(p => {
        p.day = null
      })

      result.forEach((dayPlan, index) => {
        dayPlan.points.forEach(p => {
          const point = points.value.find(pp => pp.id === p.id)
          if (point) {
            point.day = index + 1
          }
        })
      })

      itinerary.value = result
    } catch (e) {
      error.value = e.message || '路线规划失败'
    } finally {
      loading.value = false
    }
  }

  function selectPoint(id) {
    selectedPointId.value = id
  }

  function clearSelection() {
    selectedPointId.value = null
  }

  function reset() {
    bangumi.value = null
    points.value = []
    selectedPointId.value = null
    itinerary.value = []
    days.value = 1
    error.value = null
    searchResults.value = []
  }

  async function searchByKey(keyword) {
    if (!keyword || !keyword.trim()) {
      searchResults.value = []
      return
    }
    searching.value = true
    error.value = null
    try {
      searchResults.value = await searchBangumiByKey(keyword.trim())
    } catch (e) {
      error.value = e.message || '搜索失败'
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  function clearSearchResults() {
    searchResults.value = []
  }

  function addToLibrary(point) {
    if (!point || !point.geo) return
    const exists = coordinateLibrary.value.some(e => e.id === point.id)
    if (exists) return
    coordinateLibrary.value.push({
      id: point.id,
      name: point.name,
      originalName: point.originalName || '',
      image: point.image || '',
      ep: point.ep,
      s: point.s,
      geo: point.geo,
      origin: point.origin || '',
      originURL: point.originURL || '',
      bangumiId: bangumi.value ? bangumi.value.id : null,
      bangumiName: (bangumi.value && (bangumi.value.cn || bangumi.value.title)) || '',
      checked: true
    })
  }

  function removeFromLibrary(pointId) {
    coordinateLibrary.value = coordinateLibrary.value.filter(e => e.id !== pointId)
    libraryItinerary.value = []
  }

  function isInLibrary(pointId) {
    return coordinateLibrary.value.some(e => e.id === pointId)
  }

  function toggleLibraryItem(pointId) {
    const entry = coordinateLibrary.value.find(e => e.id === pointId)
    if (entry) entry.checked = !entry.checked
  }

  function libraryCheckAll() {
    coordinateLibrary.value.forEach(e => { e.checked = true })
  }

  function libraryUncheckAll() {
    coordinateLibrary.value.forEach(e => { e.checked = false })
  }

  function libraryRemoveSelected() {
    coordinateLibrary.value = coordinateLibrary.value.filter(e => !e.checked)
    libraryItinerary.value = []
  }

  async function generateLibraryItinerary() {
    const selected = librarySelected.value
    if (selected.length === 0) return
    loading.value = true
    libraryAiResponse.value = ''
    try {
      const config = activeAiConfig.value
      console.log('[AI] config:', JSON.stringify(config))
      console.log('[AI] aiConfig:', JSON.stringify(aiConfig.value))
      const result = await generateAIRoute(
        libraryDays.value,
        selected,
        config,
        (text) => {
          libraryAiResponse.value = text
        }
      )
      libraryAiResponse.value = result
      // L2: 快照生成时的选中地标（深拷贝，不受后续 checkbox 变更影响）
      generatedLandmarks.value = selected.map(lm => ({ ...lm }))
      // H1: 仅有效 markdown（非纯 __STATUS__/__ERROR__）才存历史，避免脏数据入库
      const hasMarkdown = result
        .split('\n')
        .filter(l => !l.startsWith('__STATUS__:') && !l.startsWith('__ERROR__:'))
        .join('')
        .trim()
      if (hasMarkdown) {
        saveRouteHistory(selected, result, libraryDays.value, aiConfig.value.scheme)
      }
    } catch (e) {
      error.value = e.message || 'AI 路线规划失败'
    } finally {
      loading.value = false
    }
  }

  function toggleCheck(id) {
    const point = points.value.find(p => p.id === id)
    if (point) {
      point.checked = !point.checked
    }
  }

  function checkAll() {
    points.value.forEach(p => { p.checked = true })
  }

  function uncheckAll() {
    points.value.forEach(p => { p.checked = false })
  }

  function invertCheck() {
    points.value.forEach(p => { p.checked = !p.checked })
  }

  return {
    showAdminPage,
    bangumi,
    points,
    selectedPointId,
    selectedPoint,
    checkedPoints,
    checkedCount,
    allChecked,
    someChecked,
    itinerary,
    days,
    loading,
    error,
    searchResults,
    searching,
    defaultCenter,
    defaultZoom,
    coordinateLibrary,
    libraryItinerary,
    libraryDays,
    librarySelected,
    libraryAiResponse,
    generatedLandmarks,
    routeHistory,
    compareData,
    searchBangumi,
    generateItinerary,
    selectPoint,
    clearSelection,
    reset,
    searchByKey,
    clearSearchResults,
    addToLibrary,
    removeFromLibrary,
    isInLibrary,
    toggleLibraryItem,
    libraryCheckAll,
    libraryUncheckAll,
    libraryRemoveSelected,
    generateLibraryItinerary,
    aiConfig,
    activeAiConfig,
    updateAiConfig,
    saveAiConfig,
    saveRouteHistory,
    deleteRouteHistory,
    clearRouteHistory,
    toggleCheck,
    checkAll,
    uncheckAll,
    invertCheck
  }
})
