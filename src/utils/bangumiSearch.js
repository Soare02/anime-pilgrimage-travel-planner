function normalizeKeyword(value) {
  return String(value || '').normalize('NFKC').toLowerCase().replace(/[\s\p{P}\p{S}]/gu, '')
}

function onlineError(error) {
  const prefix = '本地作品库未匹配，'
  const status = error.response?.status
  if (status === 429) return new Error(prefix + '在线搜索请求过于频繁，请稍后重试', { cause: error })
  if (status) return new Error(prefix + `在线搜索服务返回错误 (${status})，请稍后重试`, { cause: error })
  if (['ECONNABORTED', 'ETIMEDOUT'].includes(error.code) || error.name === 'TimeoutError') {
    return new Error(prefix + '在线搜索超时，请重试或直接输入 Bangumi ID', { cause: error })
  }
  return new Error(prefix + '在线搜索连接失败，请检查网络或直接输入 Bangumi ID', { cause: error })
}

export function createBangumiSearcher(entries, requestOnline) {
  const index = entries.map(entry => ({
    entry,
    names: [entry.name_cn, entry.name, entry.name_en, ...(entry.aliases || [])]
      .map(normalizeKeyword).filter(Boolean)
  }))

  return async function searchBangumiByKey(keyword, { signal } = {}) {
    signal?.throwIfAborted()
    const query = normalizeKeyword(keyword)
    if (!query) return []

    const matches = index.map(({ entry, names }) => ({
      entry,
      rank: names.some(name => name === query) ? 0
        : names.some(name => name.startsWith(query)) ? 1
          : names.some(name => name.includes(query)) ? 2 : 3
    })).filter(match => match.rank < 3).sort((a, b) => a.rank - b.rank)

    // 命中本地快照时立即返回，不等待或请求任何在线搜索服务。
    if (matches.length) {
      return matches.slice(0, 10).map(({ entry }) => ({
        id: entry.id,
        name: entry.name,
        name_cn: entry.name_cn,
        image: entry.image ? `${entry.image}${entry.image.includes('?') ? '&' : '?'}plan=h160` : '',
        air_date: '',
        summary: ''
      }))
    }

    let data
    try {
      data = await requestOnline(String(keyword).trim(), { signal })
      signal?.throwIfAborted()
    } catch (error) {
      if (signal?.aborted || error.code === 'ERR_CANCELED' || error.name === 'AbortError') throw error
      throw onlineError(error)
    }

    // Anitabi 的在线搜索返回数组，title 是显示名称，sub 是作品原名。
    // HTML/错误对象不能被当成“没有作品”，否则会掩盖代理失效。
    if (!Array.isArray(data) || data.some(item => !item ||
      !Number.isSafeInteger(Number(item.id)) || Number(item.id) <= 0 || typeof item.title !== 'string')) {
      throw new Error('在线搜索返回的数据格式异常，请稍后重试')
    }
    const seen = new Set()
    return data.filter(item => {
      const id = Number(item.id)
      if (seen.has(id)) return false
      seen.add(id)
      return true
    }).slice(0, 10).map(item => ({
      id: Number(item.id),
      name: item.sub || item.title,
      name_cn: item.title,
      image: item.cover || '',
      air_date: '',
      summary: item.tip || ''
    }))
  }
}
