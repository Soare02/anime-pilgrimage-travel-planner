import test from 'node:test'
import assert from 'node:assert/strict'
import { applyPlanningStep, finishPlanningSteps, groupPlanningSteps, normalizePlanningStep, restorePlanningSteps } from '../src/utils/planningProgress.js'

const start = '2026-10-26T12:00:00.000Z'
const finish = '2026-10-26T12:00:03.000Z'
function step(stage, sequence, options = {}) {
  const attempt = options.attempt || 1
  return { id: `phase:${stage}:${attempt}`, stage, kind: 'phase', status: 'running', title: stage, summary: '正在执行',
    started_at: start, sequence, order: sequence, attempt, ...options }
}

test('updates keep completed records and ignore duplicate or stale events', () => {
  let steps = applyPlanningStep([], step('retrieve', 1))
  steps = applyPlanningStep(steps, step('experience', 2))
  steps = applyPlanningStep(steps, step('retrieve', 3, { status: 'completed', summary: '命中 4 处', finished_at: finish, duration_ms: 3000 }))
  assert.equal(steps.length, 2)
  assert.equal(steps[0].summary, '命中 4 处')
  assert.equal(steps[0].status, 'completed')
  assert.equal(applyPlanningStep(steps, step('retrieve', 1)), steps)
  assert.equal(applyPlanningStep(steps, step('retrieve', 4)), steps)
})

test('repair activity is grouped under validation without changing the initial route stage', () => {
  const steps = restorePlanningSteps([
    step('route', 1, { status: 'completed', summary: '初稿已生成' }),
    step('validate', 2, { status: 'warning', summary: '发现 1 处遗漏' }),
    step('route', 3, { attempt: 2, summary: '正在补排', title: '路线重排 · 第 1 次' })
  ])
  let groups = groupPlanningSteps(steps, 'running', Date.parse(finish))
  assert.equal(groups.find(group => group.id === 'route').status, 'completed')
  const repairing = groups.find(group => group.id === 'validate')
  assert.equal(repairing.status, 'running')
  assert.equal(repairing.details.length, 2)
  assert.ok(repairing.details.some(detail => detail.summary === '发现 1 处遗漏'))
  const rerouted = applyPlanningStep(steps, step('route', 4, { attempt: 2, status: 'completed', summary: '补排初稿已生成' }))
  groups = groupPlanningSteps(rerouted, 'running')
  assert.equal(groups.find(group => group.id === 'validate').status, 'running')
  const checked = applyPlanningStep(rerouted, step('validate', 5, { attempt: 2, status: 'completed', summary: '全部 6 处通过校验' }))
  const completed = groupPlanningSteps(checked, 'success').find(group => group.id === 'validate')
  assert.equal(completed.status, 'completed')
  assert.equal(completed.summary, '全部 6 处通过校验')
  assert.ok(completed.details.some(detail => detail.summary === '发现 1 处遗漏'))
})

test('cancellation preserves previous summaries and leaves future stages unexecuted', () => {
  const steps = restorePlanningSteps([
    step('input', 1, { status: 'completed', summary: '读取 6 处地点' }), step('retrieve', 2)
  ])
  const cancelled = finishPlanningSteps(steps, 'cancelled', finish)
  assert.equal(cancelled[0].summary, '读取 6 处地点')
  assert.equal(cancelled[1].status, 'cancelled')
  assert.equal(cancelled[1].duration_ms, 3000)
  const groups = groupPlanningSteps(cancelled, 'cancelled')
  assert.equal(groups.find(group => group.id === 'enrich').status, 'skipped')
})

test('interrupted streams cannot turn an unfinished phase into a completed phase', () => {
  const steps = restorePlanningSteps([step('route', 1)])
  const failed = finishPlanningSteps(steps, 'failed', finish, '事件流中断')
  assert.equal(failed[0].status, 'failed')
  assert.equal(failed[0].summary, '事件流中断')
  assert.equal(finishPlanningSteps(steps, 'success', finish)[0].status, 'warning')
})

test('malformed progress is ignored while valid plan data remains usable', () => {
  assert.equal(normalizePlanningStep({ stage: 'invented' }), null)
  assert.equal(normalizePlanningStep(step('route', -1)), null)
  assert.deepEqual(restorePlanningSteps(null), [])
  const steps = restorePlanningSteps([step('input', 1), { id: 'bad', stage: 'route', status: 'completed' }])
  assert.equal(steps.length, 1)
})
