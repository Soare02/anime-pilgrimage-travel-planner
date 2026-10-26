import test from 'node:test'
import assert from 'node:assert/strict'
import { createAnitabiMapClient, parseMapIndex } from '../src/utils/anitabiMapData.js'
import { getImageUrl } from '../src/utils/imageUrl.js'

// 保留官网真实字段位置；坐标和详情分别来自 g.json 与 gN.json。
const rawIndex = [[
  [287488, '佐贺偶像是传奇 复仇', 0, 'ゾンビランドサガ リベンジ', '佐贺县', '#e7bb25',
    '/images/bangumi/287488.jpg', 7.7, 'TV', 33.372977, 130.185367, 9.9,
    ['q3ndufeaf', 33.253106, 130.304381, 134, '6mxexb9', 33.251086, 130.301719, 241]],
  [115908, '吹响吧！上低音号', 0, '響け！ユーフォニアム', '宇治市', '#02a7bd', 0, 0, 'TV',
    34.90646, 135.81221, 12, ['qys7fu', 35.05038, 135.766468, 10]]
], 1, 1792886433720]
const saga = [287488, 0, [
  ['q3ndufeaf', '松原3丁目駐車場', '松原3丁目停車場', 0, 0, 0,
    '/images/user/0/bangumi/287488/points/q3ndufeaf-1731778161293.jpg', 0, 10, 1354, 0, 0,
    'https://aurakaze.blog/zls_jyunrei_sagacity/#toc12', 0, 133],
  ['6mxexb9', '鶴乃堂本舗', 0, 0, 0, 1020, 0, 0, 0, 0, 0, 0, 0, 0, 241]
], 1792746658105]
const kyoto = [115908, 0, [
  ['qys7fu', '京都コンサートホール', '京都音乐厅', 1, '13mgdlajJV0HxpqKf6ri2NnEHFBc', 0,
    '/images/points/115908/qys7fu.jpg', 0, 1, 1, 0, '日々是妄想', 0, 0, 50]
], 1784018373338]
const fixtures = { 'g.json': rawIndex, 'g0.json': [saga], 'g1.json': [kyoto] }

function fixtureClient(options) {
  const calls = []
  const client = createAnitabiMapClient(async (file, version) => {
    calls.push({ file, version })
    assert.ok(Object.hasOwn(fixtures, file), `不应请求额外数据：${file}`)
    return structuredClone(fixtures[file])
  }, options)
  return { client, calls }
}

test('按地标 ID 合并官网坐标和详情，保留图片、中文名、出处与零值时间', async () => {
  const { client } = fixtureClient()
  const lite = await client.fetchBangumiLite(287488)
  const points = await client.fetchBangumiPointsDetail('287488')
  assert.equal(lite.cn, '佐贺偶像是传奇 复仇')
  assert.deepEqual(lite.geo, [33.372977, 130.185367])
  assert.equal(lite.pointsLength, 2)
  assert.equal(lite.imagesLength, 1)
  assert.deepEqual(points.map(point => point.geo), [[33.253106, 130.304381], [33.251086, 130.301719]])
  assert.equal(points[0].cn, '松原3丁目停車場')
  assert.equal(points[0].image, 'https://img-tc.anitabi.cn/user/0/bangumi/287488/points/q3ndufeaf-1731778161293.jpg?plan=h160')
  assert.equal(lite.cover, 'https://img-tc.anitabi.cn/bangumi/287488.jpg?plan=h160')
  assert.equal(points[0].originURL, 'https://aurakaze.blog/zls_jyunrei_sagacity/#toc12')
  assert.equal(points[1].ep, 0)
  assert.equal(points[1].s, 0)
  assert.equal(points[1].origin, 'Anitabi')
  assert.equal(points[1].originURL, 'https://www.anitabi.cn/map?bangumiId=287488&pid=6mxexb9')
  assert.deepEqual((await client.fetchBangumiPointsDetail(287488, true)).map(point => point.id), ['q3ndufeaf'])
})

test('并发请求和切换作品共用索引，只加载需要的分片；UI 修改不污染缓存', async () => {
  const { client, calls } = fixtureClient()
  const [lite, points] = await Promise.all([
    client.fetchBangumiLite(287488), client.fetchBangumiPointsDetail(287488)
  ])
  assert.deepEqual(calls.map(call => call.file), ['g.json', 'g0.json'])
  assert.equal(calls[1].version, rawIndex[2])
  lite.geo[0] = 0
  points[0].geo[0] = 0
  const reloaded = await client.fetchBangumiLite(287488)
  assert.equal(reloaded.geo[0], 33.372977)
  assert.equal(reloaded.litePoints[0].geo[0], 33.253106)
  const other = await client.fetchBangumiPointsDetail(115908)
  assert.deepEqual(calls.map(call => call.file), ['g.json', 'g0.json', 'g1.json'])
  assert.match(other[0].originURL, /^https:\/\/www\.google\.com\/maps\/d\/viewer\?mid=/)
})

test('官网路径与旧图片域名使用当前图源，缩略图和对照图保留各自分辨率', () => {
  const path = '/user/0/bangumi/287488/points/q3ndufeaf-1731778161293.jpg'
  for (const source of [`/images${path}`, `https://image.anitabi.cn${path}`,
    `https://image-anitabi.magiconch.com${path}`, `http://img-tc.anitabi.cn${path}`]) {
    assert.equal(getImageUrl(source), `https://img-tc.anitabi.cn${path}?plan=h160`)
  }
  const old = `https://image.anitabi.cn${path}?plan=h160&v=12`
  assert.equal(getImageUrl(old, 'h360'), `https://img-tc.anitabi.cn${path}?plan=h360&v=12`)
  assert.equal(getImageUrl(`https://img-tc.anitabi.cn${path}?plan=h360`), `https://img-tc.anitabi.cn${path}?plan=h360`)
})

test('外部图片保留原始来源和查询参数，无效或非图片网络地址不会生成请求', () => {
  const external = 'https://www.tv-asahi.co.jp/anime/scene.jpg?size=small'
  assert.equal(getImageUrl(external, 'h360'), external)
  for (const source of [null, 0, '', 'not a url', 'javascript:alert(1)', 'file:///image.jpg']) {
    assert.equal(getImageUrl(source), '')
  }
})

test('缓存到期重新校验版本，官网更新后丢弃旧分片并使用新坐标', async () => {
  let time = 0
  let version = 0
  const calls = []
  const client = createAnitabiMapClient(async file => {
    calls.push(file)
    const data = structuredClone(fixtures[file])
    if (file === 'g.json' && version) {
      data[2]++
      data[0][0][12][1] = 33.254
    }
    return data
  }, { now: () => time, ttl: 10 })
  await client.fetchBangumiLite(287488)
  time = 10
  await client.fetchBangumiLite(287488)
  assert.deepEqual(calls, ['g.json', 'g0.json', 'g.json'])
  version++
  time = 20
  const data = await client.fetchBangumiPointsDetail(287488)
  assert.equal(data[0].geo[0], 33.254)
  assert.deepEqual(calls.slice(-2), ['g.json', 'g0.json'])
})

test('官网索引与分片排序不同时仍按作品 ID 查找', async () => {
  const client = createAnitabiMapClient(async file => structuredClone({
    ...fixtures, 'g0.json': [kyoto], 'g1.json': [saga]
  }[file]))
  assert.equal((await client.fetchBangumiPointsDetail(287488))[0].id, 'q3ndufeaf')
})

test('请求失败可以重试，不能把拒绝的 Promise 永久缓存', async () => {
  let failed = false
  let pageCalls = 0
  const client = createAnitabiMapClient(async file => {
    if (file === 'g0.json') {
      pageCalls++
      if (!failed) { failed = true; throw { response: { status: 503 } } }
    }
    return structuredClone(fixtures[file])
  })
  await assert.rejects(client.fetchBangumiLite(287488), /503/)
  assert.equal((await client.fetchBangumiLite(287488)).pointsLength, 2)
  assert.equal(pageCalls, 2)
})

test('拒绝 HTML 回退、变更的数据结构、非法坐标和不一致的地标集合', async () => {
  for (const data of ['<!doctype html>', {}, [[], 250, 1]]) {
    assert.throws(() => parseMapIndex(data), /格式异常/)
  }
  for (const lat of ['33.253106', null, 91]) {
    const data = structuredClone(rawIndex)
    data[0][0][12][1] = lat
    assert.throws(() => parseMapIndex(data), /地标坐标数据格式异常/)
  }
  let broken = true
  const client = createAnitabiMapClient(async file => {
    const data = structuredClone(fixtures[file])
    if (broken && file === 'g0.json') data[0][2].pop()
    return data
  })
  await assert.rejects(client.fetchBangumiLite(287488), /坐标与详情版本不一致/)
  broken = false
  assert.equal((await client.fetchBangumiLite(287488)).pointsLength, 2)
})

test('无效 ID、未收录作品、网络限制和超时给出明确错误', async () => {
  const { client, calls } = fixtureClient()
  await assert.rejects(client.fetchBangumiLite('abc'), /有效的 Bangumi ID/)
  assert.equal(calls.length, 0)
  await assert.rejects(client.fetchBangumiLite(99999999), /未找到 ID/)
  assert.deepEqual(calls.map(call => call.file), ['g.json'])
  for (const [error, message] of [
    [{ response: { status: 403 } }, /403/],
    [{ response: { status: 429 } }, /过于频繁/],
    [{ code: 'ECONNABORTED' }, /加载超时/]
  ]) {
    const broken = createAnitabiMapClient(async () => { throw error })
    await assert.rejects(broken.fetchBangumiLite(287488), message)
  }
})

test('现有搜索与收藏流程直接使用官网坐标，API 请求全部经过同源地图代理', async () => {
  const { default: axios } = await import('axios')
  const { createServer } = await import('vite')
  const { createPinia, setActivePinia } = await import('pinia')
  const previousAdapter = axios.defaults.adapter
  const previousStorage = globalThis.localStorage
  const calls = []
  axios.defaults.adapter = async config => {
    calls.push(config.url)
    assert.match(config.url, /^\/anitabi-data\/g\d*\.json$/)
    const data = fixtures[config.url.split('/').pop()]
    assert.ok(data)
    return { data: structuredClone(data), status: 200, statusText: 'OK', headers: {}, config }
  }
  globalThis.localStorage = { getItem: () => null, setItem() {} }
  let vite
  try {
    vite = await createServer({ configFile: false,
      cacheDir: `verification_artifacts/vite-map-tests-${process.pid}`,
      server: { middlewareMode: true, hmr: false },
      appType: 'custom', optimizeDeps: { noDiscovery: true } })
    const { useAppStore } = await vite.ssrLoadModule('/src/stores/app.js')
    setActivePinia(createPinia())
    const store = useAppStore()
    await store.searchBangumi(287488)
    assert.equal(store.bangumi.cn, '佐贺偶像是传奇 复仇')
    assert.equal(store.points.length, 1)
    assert.deepEqual([...store.points[0].geo], [33.253106, 130.304381])
    store.addToLibrary(store.points[0])
    assert.deepEqual([...store.coordinateLibrary[0].geo], [33.253106, 130.304381])
    assert.deepEqual(calls, ['/anitabi-data/g.json', '/anitabi-data/g0.json'])
  } finally {
    axios.defaults.adapter = previousAdapter
    globalThis.localStorage = previousStorage
    await vite?.close()
  }
})
