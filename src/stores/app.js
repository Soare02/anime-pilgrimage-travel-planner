import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchBangumiLite, fetchBangumiPointsDetail, searchBangumiByKey, generateAIRoute } from '../utils/api'
import { planRoute } from '../utils/routePlanner'

export const useAppStore = defineStore('app', () => {
  const bangumi = ref(null)
  const points = ref([])
  const selectedPointId = ref(null)
  const mapFocusRequest = ref(0)
  const itinerary = ref([])
  const days = ref(1)
  const loading = ref(false)
  const planning = ref(false)
  const error = ref(null)
  const searchResults = ref([])
  const searching = ref(false)
  let searchRequestId = 0
  let searchController = null

  const coordinateLibrary = ref([])
  const libraryItinerary = ref([])
  const libraryDays = ref(1)
  const libraryAiResponse = ref('')
  const generatedLandmarks = ref([])
  const currentRequestSnapshot = ref(null)
  const currentRunId = ref(null)
  const currentPlan = ref(null)
  const historyPlan = ref(null)
  const historyLandmarks = ref([])
  const planningProgress = ref('')
  const runStatus = ref('idle')
  const historySaveError = ref('')
  const routeHistory = ref(loadRouteHistory())
  let planningRequestId = 0
  let planningController = null
  const compareData = ref(null)
  const showAdminPage = ref(false)
  const activePanel = ref('explore')
  const settingsOpen = ref(false)
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
        url: '/api/v2/agent/plan',
        apiKey: '',
        model: ''
      }
    }
    try {
      const saved = localStorage.getItem('ai-config')
      if (saved) {
        const parsed = JSON.parse(saved)
        const savedAgent = { ...defaultConfig.agent, ...(parsed.agent || {}) }
        if (savedAgent.url === '/api/agent/plan') savedAgent.url = defaultConfig.agent.url
        return {
          ...defaultConfig,
          ...parsed,
          cloud: { ...defaultConfig.cloud, ...(parsed.cloud || {}) },
          local: { ...defaultConfig.local, ...(parsed.local || {}) },
          agent: savedAgent
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
      const parsed = saved ? JSON.parse(saved) : []
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  function persistRouteHistory(nextHistory) {
    try {
      localStorage.setItem('route-history', JSON.stringify(nextHistory))
      routeHistory.value = nextHistory
      historySaveError.value = ''
      return true
    } catch (e) {
      console.warn('Failed to save route history:', e)
      historySaveError.value = '本次结果未保存到历史，请检查浏览器存储空间'
      return false
    }
  }

  function saveRouteHistory(landmarks, aiResponse, days, scheme, plan = null) {
    const snapshot = cloneLandmarks(landmarks)
    const record = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      timestamp: Date.now(),
      days,
      landmarks: snapshot.map(lm => ({ id: lm.id, bangumiId: lm.bangumiId })),
      aiResponse,
      scheme
    }
    if (plan) {
      record.schema_version = 1
      record.plan = plan
      record.landmarkSnapshot = snapshot
    }
    return persistRouteHistory([...routeHistory.value, record])
  }

  function deleteRouteHistory(id) {
    persistRouteHistory(routeHistory.value.filter(h => h.id !== id))
  }

  function clearRouteHistory() {
    persistRouteHistory([])
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
    clearSearchResults()
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
    mapFocusRequest.value++
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
    clearSearchResults()
    if (!keyword || !keyword.trim()) {
      return
    }
    const requestId = ++searchRequestId
    const controller = new AbortController()
    searchController = controller
    searching.value = true
    error.value = null
    try {
      const results = await searchBangumiByKey(keyword.trim(), { signal: controller.signal })
      if (requestId === searchRequestId) searchResults.value = results
    } catch (e) {
      if (requestId === searchRequestId) {
        error.value = e.message || '搜索失败'
        searchResults.value = []
      }
    } finally {
      if (requestId === searchRequestId) {
        searching.value = false
        searchController = null
      }
    }
  }

  function clearSearchResults() {
    searchRequestId++
    searchController?.abort()
    searchController = null
    searching.value = false
    searchResults.value = []
  }

  function addToLibrary(point) {
    if (!point) return
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
      bangumiOriginalName: (bangumi.value && bangumi.value.title) || '',
      checked: true
    })
  }

  function removeFromLibrary(pointId) {
    coordinateLibrary.value = coordinateLibrary.value.filter(e => e.id !== pointId)
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
  }

  function cloneLandmarks(landmarks) {
    return JSON.parse(JSON.stringify(landmarks))
  }

  function itineraryFromPlan(plan, landmarks) {
    const byId = new Map(landmarks.map(lm => [String(lm.id), lm]))
    return (plan?.days || []).map(day => ({
      day: day.day,
      points: (day.point_ids || []).map(id => byId.get(String(id))).filter(Boolean),
      distance: Number.isFinite(day.straight_line_distance_m)
        ? day.straight_line_distance_m / 1000
        : 0,
      distanceType: 'straight_line'
    }))
  }

  function fallbackPlanText(plan, landmarks) {
    const byId = new Map(landmarks.map(lm => [String(lm.id), lm]))
    const lines = [plan.status === 'draft' ? '规划未通过，以下为草案' : '巡礼路线']
    for (const day of plan.days || []) {
      const names = (day.point_ids || []).map(id => byId.get(String(id))?.name || String(id))
      lines.push(`\n第 ${day.day} 天：${names.length ? names.join(' → ') : '没有安排选中的点位'}`)
      lines.push(`点位间直线距离：${((day.straight_line_distance_m || 0) / 1000).toFixed(2)} 公里`)
    }
    if (plan.unassigned_point_ids?.length) {
      lines.push(`\n未安排：${plan.unassigned_point_ids.map(id => byId.get(String(id))?.name || String(id)).join('、')}`)
    }
    for (const issue of plan.validation?.errors || []) lines.push(`问题：${issue.message || issue.code}`)
    return lines.join('\n')
  }

  function cancelLibraryItinerary() {
    if (!planningController) return
    planningRequestId++
    planningController.abort()
    planningController = null
    planning.value = false
    loading.value = false
    planningProgress.value = '已取消路线规划'
    runStatus.value = 'cancelled'
    libraryAiResponse.value = ''
  }

  function restoreRouteHistory(record, legacyLandmarks = []) {
    cancelLibraryItinerary()
    currentPlan.value = null
    historyPlan.value = null
    historyLandmarks.value = cloneLandmarks(
      record?.landmarkSnapshot || record?.plan?.request_snapshot?.landmarks || legacyLandmarks
    )
    libraryItinerary.value = []
    generatedLandmarks.value = []
    currentRequestSnapshot.value = null
    currentRunId.value = null
    error.value = null
    planningProgress.value = ''
    libraryAiResponse.value = record?.aiResponse || ''
    if (!record?.plan) {
      runStatus.value = 'idle'
      return false
    }
    const plan = record.plan
    const snapshot = historyLandmarks.value
    generatedLandmarks.value = cloneLandmarks(snapshot)
    currentRequestSnapshot.value = {
      days: record.days || plan.request_snapshot?.days || 1,
      landmarks: cloneLandmarks(snapshot)
    }
    currentPlan.value = plan
    historyPlan.value = plan
    currentRunId.value = plan.run_id || null
    libraryItinerary.value = itineraryFromPlan(plan, generatedLandmarks.value)
    libraryAiResponse.value = record.aiResponse || fallbackPlanText(plan, generatedLandmarks.value)
    libraryDays.value = record.days || plan.request_snapshot?.days || libraryDays.value
    runStatus.value = plan.status === 'complete' ? 'success' : 'failed'
    return true
  }

  async function generateLibraryItinerary() {
    const selected = cloneLandmarks(librarySelected.value)
    if (selected.length === 0) return
    planningController?.abort()
    const requestId = ++planningRequestId
    const controller = new AbortController()
    planningController = controller
    const requestDays = libraryDays.value
    const scheme = aiConfig.value.scheme
    const config = { ...activeAiConfig.value }
    loading.value = true
    planning.value = true
    error.value = null
    historySaveError.value = ''
    planningProgress.value = scheme === 'agent' ? '正在启动智能体规划' : ''
    runStatus.value = 'running'
    currentRunId.value = `request-${requestId}`
    currentPlan.value = null
    historyPlan.value = null
    libraryItinerary.value = []
    generatedLandmarks.value = selected
    currentRequestSnapshot.value = { days: requestDays, landmarks: cloneLandmarks(selected) }
    libraryAiResponse.value = ''
    try {
      const result = await generateAIRoute(
        requestDays,
        selected,
        config,
        (text) => {
          if (requestId === planningRequestId) libraryAiResponse.value = text
        },
        {
          scheme,
          signal: controller.signal,
          onEvent(event) {
            if (requestId !== planningRequestId) return
            if (event.type === 'run_started') currentRunId.value = event.run_id
            if (event.type === 'progress') {
              planningProgress.value = event.payload.message || event.payload.status || event.payload.stage || '正在规划路线'
            }
          }
        }
      )
      if (requestId !== planningRequestId) return
      if (typeof result === 'string') {
        libraryAiResponse.value = result
        runStatus.value = 'success'
        const hasMarkdown = result.split('\n')
          .filter(line => !line.startsWith('__STATUS__:') && !line.startsWith('__ERROR__:'))
          .join('').trim()
        if (hasMarkdown) saveRouteHistory(selected, result, requestDays, scheme)
      } else {
        currentRunId.value = result.runId
        currentPlan.value = result.plan
        libraryItinerary.value = itineraryFromPlan(result.plan, selected)
        libraryAiResponse.value = result.text || fallbackPlanText(result.plan, selected)
        runStatus.value = result.status
        if (result.status === 'success') {
          saveRouteHistory(selected, libraryAiResponse.value, requestDays, scheme, result.plan)
        } else {
          error.value = result.error?.message || result.plan.validation?.errors?.[0]?.message || '规划未通过，以下为草案'
        }
      }
    } catch (e) {
      if (requestId !== planningRequestId) return
      libraryAiResponse.value = ''
      if (e?.name === 'AbortError' || e?.code === 'RUN_CANCELLED') {
        runStatus.value = 'cancelled'
        planningProgress.value = '已取消路线规划'
        error.value = e?.code === 'RUN_CANCELLED' ? e.message : null
      } else {
        runStatus.value = 'failed'
        error.value = e.message || 'AI 路线规划失败'
      }
    } finally {
      if (requestId === planningRequestId) {
        loading.value = false
        planning.value = false
        planningController = null
      }
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
    activePanel,
    settingsOpen,
    bangumi,
    points,
    selectedPointId,
    mapFocusRequest,
    selectedPoint,
    checkedPoints,
    checkedCount,
    allChecked,
    someChecked,
    itinerary,
    days,
    loading,
    planning,
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
    currentRequestSnapshot,
    currentRunId,
    currentPlan,
    historyPlan,
    historyLandmarks,
    planningProgress,
    runStatus,
    historySaveError,
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
    cancelLibraryItinerary,
    restoreRouteHistory,
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
