import test from 'node:test'
import assert from 'node:assert/strict'
import { createAdminApi } from '../src/admin/api.js'

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

test('admin login and management writes use private cookie sessions and a CSRF header', async () => {
  const calls = []
  const api = createAdminApi({ fetchImpl: async (path, options) => {
    calls.push({ path, ...options })
    if (path === '/api/admin/login') return json({ username: 'admin', csrf_token: 'csrf-test', expires_at: 1234 })
    return json({ status: 'success' })
  } })
  assert.deepEqual(await api.login('admin', 'password-test'), { username: 'admin', expiresAt: 1234 })
  assert.equal(calls[0].headers.get('X-Admin-Request'), '1')
  assert.equal(calls[0].headers.get('Content-Type'), 'application/json')
  await api.request('/api/rag/clear', { method: 'POST' })
  assert.equal(calls[1].headers.get('X-CSRF-Token'), 'csrf-test')
  assert.equal(calls[1].credentials, 'same-origin')
  assert.equal(calls[1].cache, 'no-store')
  assert.equal(calls[1].redirect, 'error')
  assert.equal(calls[1].headers.get('Authorization'), null)
})

test('restoring a session restores CSRF protection for writes', async () => {
  const calls = []
  const api = createAdminApi({ fetchImpl: async (path, options) => {
    calls.push({ path, ...options })
    return path === '/api/admin/session'
      ? json({ username: 'admin', csrf_token: 'restored-csrf', expires_at: 1234 }) : json({})
  } })
  await api.getSession()
  await api.request('/api/rag/landmarks/A', { method: 'DELETE' })
  assert.equal(calls[1].headers.get('X-CSRF-Token'), 'restored-csrf')
})

test('expired sessions notify the login gate, clear CSRF state and do not expose response data', async () => {
  let unauthorized = 0
  const calls = []
  const api = createAdminApi({ onUnauthorized: () => { unauthorized++ }, fetchImpl: async (path, options) => {
    calls.push({ path, ...options })
    if (path === '/api/admin/login') return json({ username: 'admin', csrf_token: 'old-csrf', expires_at: 1234 })
    return json({ detail: '请先登录管理员账号。' }, 401)
  } })
  await api.login('admin', 'password-test')
  await assert.rejects(api.request('/api/rag/pending'), error => error.status === 401)
  assert.equal(unauthorized, 1)
  await assert.rejects(api.request('/api/rag/clear', { method: 'POST' }))
  assert.equal(calls[2].headers.get('X-CSRF-Token'), null)
})

test('invalid credentials show a login error without treating it as an expired session', async () => {
  let unauthorized = 0
  const api = createAdminApi({ onUnauthorized: () => { unauthorized++ },
    fetchImpl: async () => json({ detail: '管理员账号或密码错误。' }, 401) })
  await assert.rejects(api.login('wrong', 'wrong'), { message: '管理员账号或密码错误。', status: 401 })
  assert.equal(unauthorized, 0)
})

test('logout clears CSRF state after the server revokes the session', async () => {
  const calls = []
  const api = createAdminApi({ fetchImpl: async (path, options) => {
    calls.push({ path, ...options })
    return path === '/api/admin/login'
      ? json({ username: 'admin', csrf_token: 'csrf-test', expires_at: 1234 }) : json({})
  } })
  await api.login('admin', 'password-test')
  await api.logout()
  assert.equal(calls[1].path, '/api/admin/logout')
  assert.equal(calls[1].headers.get('X-CSRF-Token'), 'csrf-test')
  await api.request('/api/rag/pending/reject', { method: 'POST' })
  assert.equal(calls[2].headers.get('X-CSRF-Token'), null)
})
