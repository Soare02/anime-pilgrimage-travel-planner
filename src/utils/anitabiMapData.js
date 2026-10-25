import { getImageUrl as imageUrl } from './imageUrl.js'

const CACHE_TTL = 30 * 60 * 1000

export class AnitabiMapDataError extends Error {
  constructor(message, options) {
    super(message, options)
    this.name = 'AnitabiMapDataError'
  }
}

function invalidData(part) {
  return new AnitabiMapDataError(`Anitabi 官网${part}数据格式异常，请稍后重试`)
}

function inconsistentData() {
  const error = new AnitabiMapDataError('Anitabi 官网坐标与详情版本不一致，请稍后重新加载')
  error.code = 'MAP_VERSION_MISMATCH'
  return error
}

function hasGeo(geo) {
  return Array.isArray(geo) && geo.length === 2 && geo.every(Number.isFinite) &&
    Math.abs(geo[0]) <= 90 && Math.abs(geo[1]) <= 180
}

const text = value => typeof value === 'string' ? value : ''
const httpUrl = value => /^https?:\/\//i.test(text(value)) ? value : ''

// 官网 g.json: [作品数组, 每个详情分片的作品数, 数据版本时间戳]。
// 每部作品的第 12 项按 [地标 ID, 纬度, 经度, 优先级] 循环存储。
export function parseMapIndex(data) {
  if (!Array.isArray(data) || !Array.isArray(data[0]) || !data[0].length ||
      !Number.isSafeInteger(data[1]) || data[1] <= 0 || !Number.isSafeInteger(data[2]) || data[2] <= 0) {
    throw invalidData('地图索引')
  }
  const byId = new Map()
  for (const [position, row] of data[0].entries()) {
    if (!Array.isArray(row) || !Number.isSafeInteger(row[0]) || row[0] <= 0 ||
        byId.has(row[0]) || !(text(row[3]) || text(row[1])) ||
        !Array.isArray(row[12]) || row[12].length % 4 !== 0) {
      throw invalidData('作品索引')
    }
    const coordinates = new Map()
    for (let i = 0; i < row[12].length; i += 4) {
      const [id, lat, lng, priority] = row[12].slice(i, i + 4)
      if (typeof id !== 'string' || !id || coordinates.has(id) || !hasGeo([lat, lng])) {
        throw invalidData('地标坐标')
      }
      coordinates.set(id, { geo: [lat, lng], priority })
    }
    byId.set(row[0], {
      id: row[0], cn: text(row[1]), title: text(row[3]), city: text(row[4]),
      color: text(row[5]), cover: imageUrl(row[6]),
      geo: hasGeo([row[9], row[10]]) ? [row[9], row[10]] : undefined,
      zoom: Number.isFinite(row[11]) ? row[11] : undefined,
      page: Math.floor(position / data[1]), coordinates
    })
  }
  return { byId, pageCount: Math.ceil(data[0].length / data[1]), modified: data[2] }
}

export function parseMapDetailPage(data) {
  if (!Array.isArray(data) || data.some(row => !Array.isArray(row) ||
      !Number.isSafeInteger(row[0]) || !Array.isArray(row[2]) ||
      row[2].some(point => !Array.isArray(point) || point.length < 13 || typeof point[0] !== 'string'))) {
    throw invalidData('地标详情')
  }
  const byId = new Map(data.map(row => [row[0], row]))
  if (byId.size !== data.length) throw invalidData('地标详情')
  return byId
}

function mergeBangumi(metadata, detail, sourceModified) {
  const points = detail[2].map(row => {
    const coordinate = metadata.coordinates.get(row[0])
    if (!coordinate) throw inconsistentData()
    const pointUrl = `https://www.anitabi.cn/map?bangumiId=${metadata.id}&pid=${encodeURIComponent(row[0])}`
    const originLink = httpUrl(row[12])
    const mid = text(row[4])
    return {
      id: row[0], name: text(row[1]) || text(row[2]) || `${metadata.cn || metadata.title}取景地`,
      cn: text(row[2]), geo: [...coordinate.geo], priority: coordinate.priority,
      image: imageUrl(row[6]), ep: row[8] ?? undefined, s: row[9],
      isFolder: Boolean(row[3]), fid: text(row[7]), folder: text(row[13]),
      mark: text(row[10]), uid: row[5] || undefined, mid, originLink,
      origin: text(row[11]) || (mid ? 'Google Maps' : 'Anitabi'),
      originURL: originLink || (mid
        ? `https://www.google.com/maps/d/viewer?mid=${encodeURIComponent(mid)}&ll=${coordinate.geo.join(',')}&z=17`
        : pointUrl)
    }
  })
  if (points.length !== metadata.coordinates.size || new Set(points.map(point => point.id)).size !== points.length) {
    throw inconsistentData()
  }
  const { coordinates, page, ...bangumi } = metadata
  return {
    ...bangumi, geo: bangumi.geo && [...bangumi.geo], modified: detail[3] || sourceModified,
    points, pointsLength: points.length, imagesLength: points.filter(point => point.image).length
  }
}

function requestError(error) {
  if (error instanceof AnitabiMapDataError) return error
  const status = error.response?.status
  if (status === 429) return new AnitabiMapDataError('Anitabi 官网地图请求过于频繁，请稍后重试', { cause: error })
  if (status) return new AnitabiMapDataError(`Anitabi 官网地图数据请求失败 (${status})，请稍后重试`, { cause: error })
  if (['ECONNABORTED', 'ETIMEDOUT'].includes(error.code) || error.name === 'TimeoutError') {
    return new AnitabiMapDataError('Anitabi 官网地图数据加载超时，请重试', { cause: error })
  }
  return new AnitabiMapDataError('Anitabi 官网地图数据连接失败，请检查网络和 /anitabi-data/ 代理配置', { cause: error })
}

export function createAnitabiMapClient(requestJSON, { now = Date.now, ttl = CACHE_TTL } = {}) {
  let index = null
  let loadedAt = 0
  let indexRequest = null
  const pages = new Map()

  async function loadIndex() {
    if (index && now() - loadedAt < ttl) return index
    if (!indexRequest) {
      indexRequest = (async () => {
        const nextIndex = parseMapIndex(await requestJSON('g.json'))
        if (index?.modified !== nextIndex.modified) pages.clear()
        index = nextIndex
        loadedAt = now()
        return index
      })().finally(() => { indexRequest = null })
    }
    return indexRequest
  }

  function loadPage(page, catalog) {
    const key = `${catalog.modified}:${page}`
    if (!pages.has(key)) {
      const pending = Promise.resolve().then(() => requestJSON(`g${page}.json`, catalog.modified))
        .then(parseMapDetailPage).catch(error => {
          pages.delete(key)
          throw error
        })
      pages.set(key, pending)
    }
    return pages.get(key)
  }

  async function loadBangumi(subjectID) {
    const id = Number(subjectID)
    if (!Number.isSafeInteger(id) || id <= 0) throw new AnitabiMapDataError('请输入有效的 Bangumi ID')
    try {
      const catalog = await loadIndex()
      const metadata = catalog.byId.get(id)
      if (!metadata) throw new AnitabiMapDataError(`未找到 ID 为 ${id} 的作品巡礼数据，请确认 Bangumi ID 是否正确`)
      // 通常只需读取按索引位置计算出的一个分片；兼容官网更新时的分片重排。
      const order = [metadata.page, ...Array.from({ length: catalog.pageCount }, (_, page) => page)
        .filter(page => page !== metadata.page)]
      for (const page of order) {
        const detail = (await loadPage(page, catalog)).get(id)
        if (detail) return mergeBangumi(metadata, detail, catalog.modified)
      }
      throw new AnitabiMapDataError('Anitabi 官网详情中未找到该作品，数据可能正在更新，请稍后重试')
    } catch (error) {
      if (error.code === 'MAP_VERSION_MISMATCH') {
        index = null
        pages.clear()
      }
      throw requestError(error)
    }
  }

  return {
    async fetchBangumiLite(subjectID) {
      const { points, ...bangumi } = await loadBangumi(subjectID)
      return { ...bangumi, litePoints: points.slice(0, 10) }
    },
    async fetchBangumiPointsDetail(subjectID, haveImage = false) {
      const { points } = await loadBangumi(subjectID)
      return haveImage ? points.filter(point => point.image) : points
    }
  }
}
