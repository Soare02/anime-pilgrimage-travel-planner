import axios from 'axios'
import bangumiIndex from '../data/anitabi-search-index.json'
import { createBangumiSearcher } from './bangumiSearch'

const api = axios.create({
  timeout: 15000,
  headers: {
    'Accept': 'application/json'
  }
})

function handleError(error, subjectID) {
  if (error.response) {
    const status = error.response.status
    if (status === 404) {
      throw new Error(`未找到 ID 为 ${subjectID} 的作品巡礼数据，请确认 Bangumi ID 是否正确`)
    }
    if (status === 429) {
      throw new Error('请求过于频繁，请稍后再试')
    }
    throw new Error(`服务器返回错误 (${status})`)
  }
  if (error.code === 'ECONNABORTED') {
    throw new Error('请求超时，请检查网络连接后重试')
  }
  throw new Error('网络请求失败，请检查网络连接')
}

export async function fetchBangumiLite(subjectID) {
  try {
    const url = `https://api.anitabi.cn/bangumi/${subjectID}/lite`
    const response = await api.get(url)
    return response.data
  } catch (error) {
    handleError(error, subjectID)
  }
}

export async function fetchBangumiPointsDetail(subjectID, haveImage = false) {
  try {
    let url = `https://api.anitabi.cn/bangumi/${subjectID}/points/detail`
    if (haveImage) {
      url += '?haveImage=true'
    }
    const response = await api.get(url)
    return response.data
  } catch (error) {
    handleError(error, subjectID)
  }
}


function formatTimestamp(seconds) {
  if (!seconds && seconds !== 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export async function generateAIRoute(days, landmarks, aiConfig, onChunk) {
  const { url, apiKey, model } = aiConfig
  const isAgent = url.includes('/api/agent')

  if (isAgent) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          days,
          landmarks: landmarks.map(lm => ({
            id: lm.id,
            name: lm.name,
            originalName: lm.originalName || '',
            bangumiName: lm.bangumiName || '',
            bangumiOriginalName: lm.bangumiOriginalName || '',
            ep: lm.ep != null ? String(lm.ep) : '',
            s: lm.s ?? null,
            geo: lm.geo || null,
            image: lm.image || null
          }))
        })
      })

      if (!response.ok) {
        const errBody = await response.text()
        throw new Error(`智能体服务返回错误 (${response.status}): ${errBody}`)
      }

      if (response.body && onChunk) {
        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let fullText = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const text = decoder.decode(value, { stream: true })
          fullText += text
          onChunk(fullText)
        }
        // H1: 检测流内的 __ERROR__ 哨兵（后端中途异常时写入）
        const errorMatch = fullText.match(/__ERROR__:(.*)/)
        if (errorMatch) {
          throw new Error(errorMatch[1].trim() || 'AI 规划服务异常，请重试')
        }
        return fullText
      } else {
        return await response.text()
      }
    } catch (error) {
      if (error.message.includes('智能体服务返回错误')) throw error
      throw new Error('智能体规划服务连接失败，请确认本地 Python 后端服务是否已启动（uvicorn）')
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
