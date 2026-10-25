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
  vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
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
    error => error.code === 'INVALID_INPUT' && error.message.includes('坐标无效')
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
    request_snapshot: { days: 2, landmarks: snapshot },
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
})
