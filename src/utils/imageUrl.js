const ANITABI_IMAGE_HOST = 'img-tc.anitabi.cn'
const ANITABI_IMAGE_HOSTS = new Set([
  'image.anitabi.cn',
  'image-anitabi.magiconch.com',
  ANITABI_IMAGE_HOST
])

// 与官网地图当前的图片解析一致，也兼容旧收藏与历史快照中的图片地址。
export function getImageUrl(value, plan) {
  if (typeof value !== 'string' || !value.trim()) return ''
  let source = value.trim()
  if (source.startsWith('/images/')) source = `https://${ANITABI_IMAGE_HOST}/${source.slice(8)}`
  else if (source.startsWith('//')) source = `https:${source}`
  try {
    const url = new URL(source)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return ''
    if (ANITABI_IMAGE_HOSTS.has(url.hostname)) {
      url.protocol = 'https:'
      url.host = ANITABI_IMAGE_HOST
      if (plan || !url.searchParams.has('plan')) url.searchParams.set('plan', plan || 'h160')
    }
    return url.href
  } catch {
    return ''
  }
}
