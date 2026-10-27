export const planningStages = [
  { id: 'input', title: '确认巡礼地点' },
  { id: 'retrieve', title: '检索巡礼资料' },
  { id: 'experience', title: '分析天气与原作场景' },
  { id: 'route', title: '编排每日路线' },
  { id: 'validate', title: '校验与修复' },
  { id: 'enrich', title: '整理巡礼指南' }
]

const stages = new Set(planningStages.map(stage => stage.id))
const statuses = new Set(['running', 'completed', 'warning', 'failed', 'cancelled', 'skipped'])
const isoDate = value => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? value : null
const text = (value, limit) => typeof value === 'string' ? value.slice(0, limit) : ''

export function normalizePlanningStep(value) {
  if (!value || !stages.has(value.stage) || !statuses.has(value.status) || !['phase', 'detail'].includes(value.kind)) return null
  const id = text(value.id, 200)
  if (!id || !Number.isSafeInteger(value.sequence) || value.sequence < 1) return null
  const attempt = Number.isSafeInteger(value.attempt) && value.attempt > 0 ? value.attempt : 1
  return {
    id, stage: value.stage, group: value.stage === 'route' && attempt > 1 ? 'validate' : value.stage,
    kind: value.kind, parent_id: text(value.parent_id, 200), attempt,
    title: text(value.title, 160), summary: text(value.summary, 600), status: value.status,
    started_at: isoDate(value.started_at), finished_at: isoDate(value.finished_at),
    duration_ms: Number.isFinite(value.duration_ms) && value.duration_ms >= 0 ? value.duration_ms : null,
    sequence: value.sequence,
    order: Number.isSafeInteger(value.order) && value.order >= 0 ? value.order : value.sequence
  }
}

export function applyPlanningStep(steps, payload) {
  const step = normalizePlanningStep(payload)
  if (!step) return steps
  const index = steps.findIndex(item => item.id === step.id)
  if (index >= 0) {
    const previous = steps[index]
    if (step.sequence <= previous.sequence || (previous.status !== 'running' && step.status === 'running')) return steps
    return steps.map((item, i) => i === index ? step : item)
  }
  return steps.length < 400 ? [...steps, step] : steps
}

export function restorePlanningSteps(steps) {
  return (Array.isArray(steps) ? steps : []).reduce(applyPlanningStep, [])
}

export function finishPlanningSteps(steps, status, finishedAt, message = '') {
  const end = isoDate(finishedAt) || new Date().toISOString()
  return steps.map(step => {
    if (step.status !== 'running') return step
    return {
      ...step,
      status: status === 'cancelled' ? 'cancelled' : status === 'success' ? 'warning' : 'failed',
      summary: text(message || (status === 'cancelled' ? '此步骤已取消，之前的过程记录已保留' : '执行结束，此步骤未收到完成确认'), 600),
      finished_at: end,
      duration_ms: step.started_at ? Math.max(0, Date.parse(end) - Date.parse(step.started_at)) : step.duration_ms
    }
  })
}

export function planningDuration(step, now = Date.now()) {
  if (Number.isFinite(step.duration_ms)) return step.duration_ms
  if (!step.started_at) return 0
  const end = step.finished_at ? Date.parse(step.finished_at) : step.status === 'running' ? now : Date.parse(step.started_at)
  return Math.max(0, end - Date.parse(step.started_at))
}

export function groupPlanningSteps(steps, runStatus, now = Date.now()) {
  return planningStages.map(definition => {
    const entries = steps.filter(step => step.group === definition.id).sort((a, b) => a.order - b.order)
    const phases = entries.filter(step => step.kind === 'phase')
    const last = phases.at(-1)
    const active = phases.findLast(step => step.status === 'running')
    const waitingForRecheck = definition.id === 'validate' && last?.stage === 'route' && runStatus === 'running'
    const status = active || waitingForRecheck ? 'running' : last?.status || (runStatus === 'running' ? 'pending' : 'skipped')
    const representative = active || last
    return {
      ...definition, status,
      summary: representative?.summary || (runStatus === 'running' ? '等待前面的步骤完成' : '本次未执行此步骤'),
      duration_ms: phases.reduce((total, step) => total + planningDuration(step, now), 0),
      details: entries.filter(step => step.kind === 'detail' || (definition.id === 'validate' && phases.length > 1))
    }
  })
}

export function planningHeadline(groups, status) {
  if (status === 'success') return '行程已生成，规划过程已保留'
  if (status === 'cancelled') return '已取消规划，已完成的步骤仍可查看'
  if (status === 'failed') return '规划未完成，过程记录已保留'
  const active = groups.find(group => group.status === 'running')
  return active ? `正在${active.title}` : '正在准备下一步'
}
