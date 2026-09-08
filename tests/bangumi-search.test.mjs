import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createBangumiSearcher } from '../src/utils/bangumiSearch.js'

const cache = JSON.parse(await readFile(new URL('../src/data/anitabi-search-index.json', import.meta.url), 'utf8'))
const offline = () => { assert.fail('命中本地缓存时不能请求在线搜索') }

test('真实缓存支持中文、日文、英文和常见标点差异，断网仍可得到 ID', async () => {
  const search = createBangumiSearcher(cache.entries, offline)
  for (const keyword of ['你的名字。', '君の名は。', ' YOUR NAME. ']) {
    assert.equal((await search(keyword))[0].id, 160209)
  }
  assert.equal((await search('冰菓'))[0].id, 27364)
  assert.equal((await search('大鱼·海棠'))[0].id, 14830)
  const [item] = await search('你的名字')
  assert.match(item.image, /^https:\/\/image\.anitabi\.cn\/bangumi\/160209\.jpg\?plan=h160$/)
})

test('完整名称优先于包含此名称的其他作品，别名也可匹配', async () => {
  const search = createBangumiSearcher([
    { id: 1, name: '剧场版 测试作品', name_cn: '', aliases: [] },
    { id: 2, name: '测试作品', name_cn: '', aliases: ['别名'] }
  ], offline)
  assert.deepEqual((await search('测试作品')).map(item => item.id), [2, 1])
  assert.equal((await search('别名'))[0].id, 2)
})

test('缓存未命中时调用在线搜索，并适配 Anitabi 返回的名称、原名和 ID', async () => {
  const controller = new AbortController()
  let calls = 0
  const search = createBangumiSearcher(cache.entries, async (keyword, { signal }) => {
    calls++
    assert.equal(keyword, '缓存外测试作品xyz')
    assert.equal(signal, controller.signal)
    return [{ id: 999999, title: '测试作品', sub: 'Original title', cover: 'https://example.com/cover.jpg', tip: '作品简介' }]
  })
  assert.deepEqual(await search(' 缓存外测试作品xyz ', { signal: controller.signal }), [{
    id: 999999, name: 'Original title', name_cn: '测试作品', image: 'https://example.com/cover.jpg', air_date: '', summary: '作品简介'
  }])
  assert.equal(calls, 1)
})

test('空查询不联网，在线无结果返回空数组', async () => {
  const search = createBangumiSearcher(cache.entries, offline)
  assert.deepEqual(await search('  '), [])
  assert.deepEqual(await search(' [ ] '), [])
  assert.deepEqual(await createBangumiSearcher([], async () => [])('未知作品'), [])
})

test('超时、限流、连接失败分别提示，不能伪装成没有作品', async () => {
  for (const [error, message] of [
    [{ code: 'ECONNABORTED' }, /在线搜索超时/],
    [{ response: { status: 429 } }, /请求过于频繁/],
    [{ response: { status: 502 } }, /502/],
    [{ code: 'ERR_NETWORK' }, /在线搜索连接失败/]
  ]) {
    const search = createBangumiSearcher([], async () => { throw error })
    await assert.rejects(search('未知作品'), message)
  }
})

test('拒绝 HTML 回退页和接口错误对象，保留有效的空搜索结果', async () => {
  for (const data of ['<!doctype html>', { error: 'service unavailable' }, [{ title: '缺失 ID' }]]) {
    await assert.rejects(createBangumiSearcher([], async () => data)('未知作品'), /数据格式异常/)
  }
})

test('取消旧搜索后即使在线请求返回，也不能交付旧结果', async () => {
  const controller = new AbortController()
  let finish
  const search = createBangumiSearcher([], () => new Promise(resolve => { finish = resolve }))
  const pending = search('旧关键词', { signal: controller.signal })
  controller.abort()
  finish([{ id: 123, title: '旧结果' }])
  await assert.rejects(pending, { name: 'AbortError' })
  await assert.rejects(search('新关键词', { signal: controller.signal }), { name: 'AbortError' })
})
