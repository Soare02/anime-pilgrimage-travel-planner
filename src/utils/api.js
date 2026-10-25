import axios from 'axios'
import bangumiIndex from '../data/anitabi-search-index.json'
import { createBangumiSearcher } from './bangumiSearch'
import { createAnitabiMapClient } from './anitabiMapData'

const api = axios.create({
  timeout: 15000,
  headers: {
    'Accept': 'application/json'
  }
})

const mapData = createAnitabiMapClient(async (file, version) => {
  const response = await api.get(`/anitabi-data/${file}`, {
    params: { v: version || Math.floor(Date.now() / (30 * 60 * 1000)) }
  })
  return response.data
})

export const fetchBangumiLite = mapData.fetchBangumiLite
export const fetchBangumiPointsDetail = mapData.fetchBangumiPointsDetail


function formatTimestamp(seconds) {
  if (!seconds && seconds !== 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export class AgentRouteError extends Error {
  constructor(message, code = 'AGENT_ERROR', details = null) {
    super(message)
    this.name = 'AgentRouteError'
    this.code = code
    this.details = details
  }
}

const agentErrorMessages = {
  INVALID_INPUT: '选中的地点或天数无效，请检查后重试',
  MODEL_OUTPUT_INVALID: '智能体生成的数据无法解析，请重试',
  MISSING_LANDMARK: '有选中的地点未被安排',
  DUPLICATE_LANDMARK: '行程中有重复的地点',
  UNKNOWN_LANDMARK: '行程中出现了未选中的地点',
  DAY_COUNT_MISMATCH: '行程天数与请求不一致',
  TOOL_TIMEOUT: '资料查询超时，请稍后重试',
  MODEL_TIMEOUT: '智能体规划超时，请稍后重试',
  RUN_CANCELLED: '已取消路线规划'
}

function agentError(payload = {}) {
  const code = payload.code || 'AGENT_ERROR'
  return new AgentRouteError(payload.message || agentErrorMessages[code] || '智能体规划失败', code, payload)
}

async function responseError(response, serviceName) {
  const body = await response.text()
  let data
  try { data = JSON.parse(body) } catch { data = null }
  const detail = data?.detail
  const firstDetail = Array.isArray(detail) ? detail[0] : detail
  const message = data?.message || (typeof detail === 'string' ? detail : firstDetail?.message || firstDetail?.msg) || body.trim()
  const code = data?.code || firstDetail?.code || (response.status === 422 ? 'INVALID_INPUT' : 'HTTP_ERROR')
  return new AgentRouteError(`${serviceName}返回错误 (${response.status})：${message || response.statusText}`, code, data)
}

function parseSseEvent(block) {
  const data = block.split(/\r\n|\n|\r/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())
    .join('\n')
  if (!data) return null
  let event
  try { event = JSON.parse(data) } catch {
    throw new AgentRouteError('智能体返回了无法解析的事件数据', 'MODEL_OUTPUT_INVALID')
  }
  if (!event || !event.event_id || !event.run_id || !event.type || !event.payload || typeof event.payload !== 'object' || Array.isArray(event.payload)) {
    throw new AgentRouteError('智能体返回了不完整的事件数据', 'MODEL_OUTPUT_INVALID')
  }
  return event
}

async function readAgentEvents(response, onEvent, signal) {
  if (!response.body) {
    throw new AgentRouteError('智能体没有返回事件流', 'EVENT_STREAM_INCOMPLETE')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let runId = null
  let plan = null
  let planEventType = null
  let text = ''
  let status = null
  let reportedError = null
  let started = false

  function accept(block) {
    const event = parseSseEvent(block)
    if (!event) return
    if (runId && event.run_id !== runId) {
      throw new AgentRouteError('智能体事件的运行编号不一致', 'EVENT_STREAM_INVALID')
    }
    if (!runId) runId = event.run_id
    if (status) {
      throw new AgentRouteError('智能体在结束事件后仍返回数据', 'EVENT_STREAM_INVALID')
    }
    if (event.type === 'run_started') started = true
    if (event.type === 'plan_ready' || event.type === 'plan_draft') {
      plan = event.payload.plan || null
      planEventType = event.type
      text = typeof event.payload.text === 'string' ? event.payload.text : ''
    } else if (event.type === 'error') {
      reportedError = agentError(event.payload)
    } else if (event.type === 'run_finished') {
      status = event.payload.status
      if (!['success', 'failed', 'cancelled'].includes(status)) {
        throw new AgentRouteError('智能体返回了无效的结束状态', 'EVENT_STREAM_INVALID')
      }
    }
    onEvent?.(event)
  }

  function consume() {
    let match
    while ((match = /\r\n\r\n|\n\n|\r\r/.exec(buffer))) {
      const block = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      accept(block)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      consume()
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    }
    buffer += decoder.decode()
    consume()
    if (buffer.trim()) {
      throw new AgentRouteError('智能体事件流在事件中途断开', 'EVENT_STREAM_INCOMPLETE')
    }
    if (!started || !status) {
      throw new AgentRouteError('智能体事件流未正常结束', 'EVENT_STREAM_INCOMPLETE')
    }
    if (status === 'cancelled') throw agentError({ code: 'RUN_CANCELLED' })
    if (status === 'success' && (planEventType !== 'plan_ready' || !plan || plan.status !== 'complete' || plan.validation?.passed !== true)) {
      throw new AgentRouteError('智能体没有交付通过校验的完整行程', 'MODEL_OUTPUT_INVALID')
    }
    if (status === 'failed' && plan && (planEventType !== 'plan_draft' || plan.status !== 'draft' || plan.validation?.passed !== false)) {
      throw new AgentRouteError('智能体草案状态与运行结果不一致', 'EVENT_STREAM_INVALID')
    }
    if (status === 'failed' && !plan) throw reportedError || agentError()
    return { plan, text, runId, status, error: reportedError }
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
}

async function readLegacyAgentText(response, onChunk) {
  if (!response.body) {
    const fullText = await response.text()
    const errorMatch = fullText.match(/^__ERROR__:(.*)$/m)
    if (errorMatch) throw new AgentRouteError(errorMatch[1].trim() || '智能体规划失败')
    onChunk?.(fullText)
    return fullText
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let fullText = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
      onChunk?.(fullText)
    }
    fullText += decoder.decode()
    const errorMatch = fullText.match(/^__ERROR__:(.*)$/m)
    if (errorMatch) throw new AgentRouteError(errorMatch[1].trim() || '智能体规划失败')
    onChunk?.(fullText)
    return fullText
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
}

export async function generateAIRoute(days, landmarks, aiConfig, onChunk, options = {}) {
  const { url, apiKey, model } = aiConfig
  const { scheme, signal, onEvent } = options

  if (scheme === 'agent') {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream, text/plain' },
        signal,
        body: JSON.stringify({ days, landmarks })
      })
      if (!response.ok) throw await responseError(response, '智能体服务')
      if (response.headers.get('content-type')?.toLowerCase().includes('text/event-stream')) {
        return await readAgentEvents(response, onEvent, signal)
      }
      return await readLegacyAgentText(response, onChunk)
    } catch (error) {
      if (error?.name === 'AbortError' || error instanceof AgentRouteError) throw error
      throw new AgentRouteError('智能体规划服务连接失败，请确认本地 Python 后端服务是否已启动（uvicorn）', 'NETWORK_ERROR', error)
    }
  }

  const landmarkLines = landmarks.map((lm, i) => {
    const parts = [`${i + 1}. 地点名称：${lm.name || lm.originalName || '未知'}`]
    parts.push(`   作品名称：${lm.bangumiName || '未知'}`)
    if (lm.originalName && lm.originalName !== lm.name) parts.push(`   日文地点名：${lm.originalName}`)
    if (lm.bangumiOriginalName && lm.bangumiOriginalName !== lm.bangumiName) parts.push(`   日文作品名：${lm.bangumiOriginalName}`)
    if (lm.ep) parts.push(`   出现集数：EP${lm.ep}`)
    if (lm.s || lm.s === 0) parts.push(`   时间戳：${formatTimestamp(lm.s)}`)
    if (lm.geo) parts.push(`   坐标：${lm.geo[0]}, ${lm.geo[1]}`)
    return parts.join('\n')
  }).join('\n\n')

  const dataText = `巡礼天数：${days}天\n\n需要访问的地标（共${landmarks.length}个）：\n${landmarkLines}`

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      signal,
      body: JSON.stringify({
        model,
        stream: false,
        messages: [
          {
            role: 'user',
            content: dataText
          }
        ]
      })
    })

    if (!response.ok) {
      const errBody = await response.text()
      throw new Error(`AI 服务返回错误 (${response.status}): ${errBody}`)
    }

    const data = await response.json()
    return data.choices[0].message.content
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    if (error.message.includes('AI 服务返回错误')) throw error
    throw new Error('AI 路线规划请求失败，请检查网络连接后重试')
  }
}

export const searchBangumiByKey = createBangumiSearcher(bangumiIndex.entries, async (keyword, { signal }) => {
  const response = await api.get('/bgm/search', {
    params: { keyword, cat: 2 },
    signal
  })
  return response.data
})
