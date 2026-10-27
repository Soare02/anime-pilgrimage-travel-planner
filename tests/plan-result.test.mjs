import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createServer as createHttpServer } from 'node:http'

let vite
let PlanResult
let PlanningTimeline
const hmrServer = createHttpServer()
before(async () => {
  vite = await createServer({
    configFile: false,
    plugins: [vue()],
    cacheDir: `verification_artifacts/vite-plan-tests-${process.pid}`,
    server: { middlewareMode: true, hmr: { server: hmrServer } },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true }
  })
  PlanResult = (await vite.ssrLoadModule('/src/components/PlanResult.vue')).default
  PlanningTimeline = (await vite.ssrLoadModule('/src/components/PlanningTimeline.vue')).default
})
after(async () => { await vite?.close() })

test('itinerary renders weather, dated reasons, scene times and photo suggestions', async () => {
  const plan = {
    status: 'complete', validation: { passed: true },
    request_snapshot: { days: 1, start_date: '2026-10-26' },
    days: [{ day: 1, date: '2026-10-26', point_ids: ['bridge'], straight_line_distance_m: 0, planning_reason: '黄昏还原原作场景', weather_advice: '如遇雨请防滑' }],
    weather: [{ location: '宇治', current_summary: '晴，20°C', retrieved_at: '2026-10-26T01:00:00Z', source_url: 'https://wttr.in/Uji', forecast: [{ date: '2026-10-26', summary: '晴', rain_chance_percent: 10, hourly: [{ time: '06:00', summary: '多云', rain_chance_percent: 5 }] }] }],
    scene_preferences: [{ point_id: 'bridge', preferred_time: 'sunset', scene_summary: '桥上的黄昏场景', reason: '参考截图的光线' }],
    point_notes: [{ point_id: 'bridge', scene_atmosphere: '安静的河畔', pose_suggestions: '参照截图姿态' }]
  }
  const html = await renderToString(createSSRApp(PlanResult, {
    plan, landmarks: [{ id: 'bridge', name: '宇治桥', geo: [34.89, 135.8] }]
  }))
  for (const text of ['2026-10-26', '安排理由：', '如遇雨请防滑', '建议到访：黄昏', '桥上的黄昏场景', '安静的河畔', '参照截图姿态', '最高降雨概率 10%', '06:00 · 多云']) {
    assert.ok(html.includes(text), `missing visible content: ${text}`)
  }
})

test('older saved plans still render without weather and scene preference fields', async () => {
  const html = await renderToString(createSSRApp(PlanResult, {
    plan: { status: 'complete', validation: { passed: true }, days: [{ day: 1, point_ids: ['A'], straight_line_distance_m: 0 }] },
    landmarks: [{ id: 'A', name: '旧地点' }]
  }))
  assert.ok(html.includes('旧地点'))
  assert.ok(html.includes('行程已生成'))
  assert.equal(html.includes('天气参考与预报'), false)
})

test('timeline renders stage summaries, search supplementation and repair details', async () => {
  const steps = [
    { id: 'phase:input:1', stage: 'input', group: 'input', kind: 'phase', status: 'completed', title: '确认巡礼地点', summary: '已读取 6 处地点', sequence: 1, order: 1 },
    { id: 'phase:retrieve:1', stage: 'retrieve', group: 'retrieve', kind: 'phase', status: 'completed', title: '检索巡礼资料', summary: '知识库命中 4 处，联网补充 2 处', sequence: 2, order: 2 },
    { id: 'search:baidu', stage: 'retrieve', group: 'retrieve', kind: 'detail', status: 'completed', title: '百度 · 久美子长椅', summary: '新增 2 条来源，跳过后续备用线路', sequence: 3, order: 3 },
    { id: 'phase:validate:1', stage: 'validate', group: 'validate', kind: 'phase', status: 'warning', title: '第 1 次校验', summary: '发现 1 处遗漏', sequence: 4, order: 4 },
    { id: 'phase:route:2', stage: 'route', group: 'validate', kind: 'phase', status: 'running', title: '路线重排 · 第 1 次', summary: '正在补入遗漏地点', sequence: 5, order: 5 }
  ]
  const html = await renderToString(createSSRApp(PlanningTimeline, { steps, status: 'running' }))
  for (const text of ['规划过程', '已读取 6 处地点', '知识库命中 4 处', '百度 · 久美子长椅', '路线重排 · 第 1 次', '发现 1 处遗漏', '等待开始', '取消规划']) {
    assert.ok(html.includes(text), `missing timeline content: ${text}`)
  }
  assert.ok(html.includes('<details open'))
})

test('finished timeline keeps escaped summaries and offers no cancel action', async () => {
  const html = await renderToString(createSSRApp(PlanningTimeline, {
    status: 'success', steps: [{ id: 'phase:input:1', stage: 'input', group: 'input', kind: 'phase', status: 'completed', summary: '<script>unsafe</script>', order: 1 }]
  }))
  assert.ok(html.includes('规划过程已保留'))
  assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'))
  assert.equal(html.includes('取消规划'), false)
})
