import { mkdir, writeFile } from 'node:fs/promises'

const source = 'https://www.anitabi.cn/d/g.json'
const response = await fetch(source, { signal: AbortSignal.timeout(30000) })
if (!response.ok) throw new Error(`Anitabi 数据下载失败 (${response.status})`)
const text = await response.text()
const data = JSON.parse(text)
if (!Array.isArray(data) || !Array.isArray(data[0]) || !data[0].length) {
  throw new Error('Anitabi 数据结构异常，保留现有缓存')
}

// 官网的紧凑数组字段：id, cn, en, title, city, color, cover, ... , abbr, ... , tAbbr。
const ids = new Set()
const entries = data[0].map(row => {
  if (!Array.isArray(row) || !Number.isSafeInteger(row[0]) || row[0] <= 0 ||
      ids.has(row[0]) || typeof row[3] !== 'string' || !(row[3] || row[1])?.trim() ||
      !Array.isArray(row[12])) {
    throw new Error('Anitabi 作品字段异常，保留现有缓存')
  }
  ids.add(row[0])
  return {
    id: row[0],
    name: row[3] || row[1],
    name_cn: row[1] || '',
    name_en: row[2] || '',
    aliases: [row[13], row[17]].filter(value => typeof value === 'string' && value),
    image: (row[6] || '').replace(/^\/images\//, 'https://image.anitabi.cn/')
  }
})
const index = { source, fetchedAt: new Date().toISOString(), modified: data[2], entries }

// 先完成解析和校验再写文件；下载失败不会覆盖可用的本地数据。
await mkdir(new URL('../data/', import.meta.url), { recursive: true })
await mkdir(new URL('../src/data/', import.meta.url), { recursive: true })
await writeFile(new URL('../data/anitabi-g.json', import.meta.url), text + '\n')
await writeFile(new URL('../src/data/anitabi-search-index.json', import.meta.url), JSON.stringify(index, null, 2) + '\n')
console.log(`已更新 ${entries.length} 部作品；原始数据 ${Buffer.byteLength(text)} 字节，前端索引 ${Buffer.byteLength(JSON.stringify(index))} 字节`)
