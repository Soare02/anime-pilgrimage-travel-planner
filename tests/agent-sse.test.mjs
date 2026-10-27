import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createPinia, setActivePinia } from 'pinia'

const originalFetch = globalThis.fetch
const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key)
}

let vite
let generateAIRoute
let useAppStore
before(async () => {
  vite = await createServer({
    configFile: false,
    cacheDir: `verification_artifacts/vite-agent-tests-${process.pid}`,
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true }
  })
  ;({ generateAIRoute } = await vite.ssrLoadModule('/src/utils/api.js'))
  ;({ useAppStore } = await vite.ssrLoadModule('/src/stores/app.js'))
})
after(async () => {
  globalThis.fetch = originalFetch
  await vite?.close()
})

function envelope(type, payload, id = 1) {
  return { event_id: `event-${id}`, run_id: 'run-fixed', type, payload }
}
function sseResponse(events, splitAt = 1) {
  const encoded = new TextEncoder().encode(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''))
  const stream = new ReadableStream({
    start(controller) {
      for (let i = 0; i < encoded.length; i += splitAt) controller.enqueue(encoded.slice(i, i + splitAt))
      controller.close()
    }
  })
  return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
}
const config = { url: '/api/v2/agent/plan' }
const landmarks = [{ id: 'A', name: '宇治桥', geo: [34.89, 135.8] }]

function phase(stage, sequence, status = 'completed') {
  return { id: `phase:${stage}:1`, stage, kind: 'phase', status, title: stage, summary: `${stage} 的执行小结`,
    sequence, order: sequence, attempt: 1, started_at: '2026-10-26T12:00:00Z',
    ...(status === 'completed' ? { finished_at: '2026-10-26T12:00:01Z', duration_ms: 1000 } : {}) }
}

test('SSE decodes split Chinese bytes and requires a terminal success', async () => {
  const plan = { status: 'complete', validation: { passed: true }, days: [{ day: 1, point_ids: ['A'] }] }
  const events = [
    envelope('run_started', { message: '开始' }, 1),
    envelope('progress', { stage: 'route', message: '正在编排行程' }, 2),
    envelope('plan_ready', { plan, text: '# 宇治桥\n' }, 3),
    envelope('run_finished', { status: 'success' }, 4)
  ]
  globalThis.fetch = async () => sseResponse(events)
  const seen = []
  const result = await generateAIRoute(1, landmarks, config, null, { scheme: 'agent', onEvent: event => seen.push(event.type) })
  assert.equal(result.status, 'success')
  assert.equal(result.text, '# 宇治桥\n')
  assert.deepEqual(seen, events.map(event => event.type))
})

test('SSE interruption cannot become a successful result', async () => {
  globalThis.fetch = async () => sseResponse([
    envelope('run_started', { message: '开始' }, 1),
    envelope('plan_ready', { plan: { status: 'complete', validation: { passed: true } }, text: '未完成' }, 2)
  ], 3)
  await assert.rejects(
    generateAIRoute(1, landmarks, config, null, { scheme: 'agent' }),
    error => error.code === 'EVENT_STREAM_INCOMPLETE'
  )
})

test('departure date is submitted only when selected', async () => {
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push(JSON.parse(options.body))
    return new Response('兼容结果', { headers: { 'content-type': 'text/plain' } })
  }
  await generateAIRoute(1, landmarks, config, null, { scheme: 'agent', startDate: '2026-10-26' })
  await generateAIRoute(1, landmarks, config, null, { scheme: 'agent' })
  assert.equal(requests[0].start_date, '2026-10-26')
  assert.equal('start_date' in requests[1], false)
})

test('draft event cannot carry a complete Plan', async () => {
  globalThis.fetch = async () => sseResponse([
    envelope('run_started', { message: '开始' }, 1),
    envelope('plan_draft', { plan: { status: 'complete', validation: { passed: true } }, text: '矛盾结果' }, 2),
    envelope('run_finished', { status: 'failed' }, 3)
  ], 7)
  await assert.rejects(
    generateAIRoute(1, landmarks, config, null, { scheme: 'agent' }),
    error => error.code === 'EVENT_STREAM_INVALID'
  )
})

test('legacy text and typed field errors stay compatible', async () => {
  globalThis.fetch = async () => new Response('旧版攻略', { headers: { 'content-type': 'text/plain' } })
  assert.equal(await generateAIRoute(1, landmarks, config, null, { scheme: 'agent' }), '旧版攻略')
  globalThis.fetch = async () => new Response(JSON.stringify({ code: 'INVALID_INPUT', message: '坐标无效', fields: [{ field: 'landmarks.0.geo', message: '坐标越界' }] }), {
    status: 422, headers: { 'content-type': 'application/json' }
  })
  await assert.rejects(
    generateAIRoute(1, landmarks, config, null, { scheme: 'agent' }),
    error => error.code === 'INVALID_INPUT' && error.message.includes('坐标越界')
  )
})

test('422 displays the failing field instead of the generic days and coordinates message', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({
    code: 'INVALID_INPUT', message: '请选择有效的天数和地标坐标后重试',
    fields: [{ field: 'landmarks.0.s', message: '第 1 个地标的场景时间无效' }]
  }), { status: 422, headers: { 'content-type': 'application/json' } })
  await assert.rejects(
    generateAIRoute(1, landmarks, config, null, { scheme: 'agent' }),
    error => error.code === 'INVALID_INPUT' && error.message.includes('第 1 个地标的场景时间无效') &&
      !error.message.includes('请选择有效的天数')
  )
})

test('saved Plan restores point order and snapshot without remote data', () => {
  storage.clear()
  setActivePinia(createPinia())
  const store = useAppStore()
  const snapshot = [
    { id: 'A', name: '宇治桥', geo: [34.89, 135.8], bangumiName: '作品甲' },
    { id: 'B', name: '宇治桥', geo: [34.9, 135.81], bangumiName: '作品乙' }
  ]
  const plan = {
    schema_version: 1, plan_id: 'plan-fixed', run_id: 'run-fixed', status: 'complete',
    request_snapshot: { days: 2, landmarks: snapshot, start_date: '2026-10-26' },
    weather: [{ location: '宇治', current_summary: '晴', forecast: [{ date: '2026-10-27', summary: '雨' }] }],
    scene_preferences: [{ point_id: 'A', preferred_time: 'sunset', reason: '还原原作黄昏场景' }],
    days: [
      { day: 1, point_ids: ['B'], legs: [], straight_line_distance_m: 0 },
      { day: 2, point_ids: ['A'], legs: [], straight_line_distance_m: 0 }
    ],
    validation: { passed: true, errors: [], warnings: [] }
  }
  store.restoreRouteHistory({ id: 'history-one', days: 2, plan, landmarkSnapshot: snapshot, aiResponse: '# 行程' })
  assert.deepEqual(store.libraryItinerary.map(day => day.points.map(point => point.id)), [['B'], ['A']])
  assert.equal(store.generatedLandmarks[0].bangumiName, '作品甲')
  assert.equal(store.currentPlan.plan_id, 'plan-fixed')
  assert.equal(store.libraryAiResponse, '# 行程')
  assert.equal(store.libraryStartDate, '2026-10-26')
  assert.equal(store.currentRequestSnapshot.start_date, '2026-10-26')
  assert.equal(store.currentPlan.weather[0].location, '宇治')
  assert.equal(store.currentPlan.scene_preferences[0].preferred_time, 'sunset')
  assert.deepEqual(store.historyLandmarks, snapshot)
  assert.deepEqual(store.coordinateLibrary, [])
})

test('legacy archive points can be focused repeatedly without changing the pilgrimage library', () => {
  storage.clear()
  setActivePinia(createPinia())
  const store = useAppStore()
  const exploration = { id: 'explore', name: '探索中的地标', geo: [35.6, 139.7] }
  const saved = { id: 'saved', name: '已有收藏', geo: [35.1, 135.7], checked: false }
  const archivePoints = [
    { id: 'archive', name: '档案地标', geo: [34.89, 135.8], bangumiId: 115908 }
  ]
  store.points = [exploration]
  store.coordinateLibrary = [saved]
  store.activePanel = 'history'
  const record = { id: 'legacy', days: 1, landmarks: [{ id: 'archive', bangumiId: 115908 }], aiResponse: '# 旧行程' }

  store.restoreRouteHistory(record, archivePoints)
  const previousFocus = store.mapFocusRequest
  store.selectPoint(store.historyLandmarks[0].id)
  store.selectPoint(store.historyLandmarks[0].id)
  assert.equal(store.selectedPointId, 'archive')
  assert.equal(store.mapFocusRequest, previousFocus + 2)
  assert.deepEqual(store.historyLandmarks, archivePoints)
  assert.deepEqual(store.coordinateLibrary, [saved])
  assert.deepEqual(store.points, [exploration])
  assert.equal(store.historyPlan, null)

  // Loading a different record cannot leave the previous archive's markers behind.
  store.restoreRouteHistory({ id: 'other', landmarks: [] })
  assert.deepEqual(store.historyLandmarks, [])
  // Reopening cached details restores the archived coordinates without collecting them.
  store.restoreRouteHistory(record, archivePoints)
  store.historyLandmarks[0].geo[0] = 0
  assert.equal(archivePoints[0].geo[0], 34.89)
  assert.deepEqual(store.coordinateLibrary, [saved])
})

test('live step summaries are retained, saved, and restored with a successful itinerary', async () => {
  storage.clear()
  setActivePinia(createPinia())
  const store = useAppStore()
  store.aiConfig.scheme = 'agent'
  store.coordinateLibrary = landmarks.map(point => ({ ...point, checked: true }))
  const plan = { status: 'complete', validation: { passed: true }, request_snapshot: { days: 1, landmarks }, days: [{ day: 1, point_ids: ['A'], straight_line_distance_m: 0 }] }
  const stages = ['input', 'retrieve', 'experience', 'route', 'validate', 'enrich']
  globalThis.fetch = async () => sseResponse([
    envelope('run_started', {}, 1),
    ...stages.map((stage, index) => envelope('step_update', phase(stage, index + 1), index + 2)),
    envelope('plan_ready', { plan, text: '# 计划' }, 8), envelope('run_finished', { status: 'success' }, 9)
  ], 9)
  await store.generateLibraryItinerary()
  assert.equal(store.runStatus, 'success')
  assert.equal(store.planningSteps.length, 6)
  assert.ok(store.planningSteps.every(step => step.status === 'completed'))
  const record = store.routeHistory.at(-1)
  assert.equal(record.planningProcess.steps[1].summary, 'retrieve 的执行小结')
  assert.ok(record.planningProcess.finished_at)
  store.planningSteps[1].summary = '更改当前显示'
  assert.equal(record.planningProcess.steps[1].summary, 'retrieve 的执行小结')
  store.restoreRouteHistory(record)
  assert.equal(store.planningSteps[1].summary, 'retrieve 的执行小结')
  assert.equal(store.planningFinishedAt, record.planningProcess.finished_at)
})

test('cancel keeps completed summaries and stops active progress without saving a success', async () => {
  storage.clear()
  setActivePinia(createPinia())
  const store = useAppStore()
  store.aiConfig.scheme = 'agent'
  store.coordinateLibrary = landmarks.map(point => ({ ...point, checked: true }))
  globalThis.fetch = async (url, options) => new Response(new ReadableStream({
    start(controller) {
      const events = [envelope('run_started', {}, 1), envelope('step_update', phase('input', 1), 2), envelope('step_update', phase('retrieve', 2, 'running'), 3)]
      controller.enqueue(new TextEncoder().encode(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')))
      options.signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true })
    }
  }), { headers: { 'content-type': 'text/event-stream' } })
  const pending = store.generateLibraryItinerary()
  for (let count = 0; count < 20 && store.planningSteps.length < 2; count++) await new Promise(resolve => setImmediate(resolve))
  assert.equal(store.planningSteps.length, 2)
  store.cancelLibraryItinerary()
  await pending
  assert.equal(store.runStatus, 'cancelled')
  assert.equal(store.planningSteps[0].status, 'completed')
  assert.equal(store.planningSteps[1].status, 'cancelled')
  assert.ok(store.planningFinishedAt)
  assert.equal(store.routeHistory.length, 0)
})

test('interrupted planning preserves completed summaries and marks the active phase failed', async () => {
  storage.clear()
  setActivePinia(createPinia())
  const store = useAppStore()
  store.aiConfig.scheme = 'agent'
  store.coordinateLibrary = landmarks.map(point => ({ ...point, checked: true }))
  globalThis.fetch = async () => sseResponse([
    envelope('run_started', {}, 1), envelope('step_update', phase('input', 1), 2), envelope('step_update', phase('route', 2, 'running'), 3)
  ], 5)
  await store.generateLibraryItinerary()
  assert.equal(store.runStatus, 'failed')
  assert.equal(store.planningSteps[0].status, 'completed')
  assert.equal(store.planningSteps[1].status, 'failed')
  assert.equal(store.routeHistory.length, 0)
})
