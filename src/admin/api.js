export class AdminApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// Session credentials stay in an HttpOnly cookie. Only the CSRF token is held
// in memory, and all administrative requests share the same expiry handling.
export function createAdminApi({ onUnauthorized = () => {}, fetchImpl = globalThis.fetch } = {}) {
  let csrfToken = ''

  function clearSession() {
    csrfToken = ''
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers)
    const method = (options.method || 'GET').toUpperCase()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      headers.set('X-Admin-Request', '1')
      if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
    }
    const response = await fetchImpl(path, {
      ...options, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error'
    })
    if (!response.ok) {
      if (response.status === 401 && path !== '/api/admin/login') {
        clearSession()
        onUnauthorized()
      }
      const body = await response.json().catch(() => null)
      const message = typeof body?.detail === 'string' ? body.detail : `管理请求失败（${response.status}）`
      throw new AdminApiError(message, response.status)
    }
    return response
  }

  async function acceptSession(response) {
    const session = await response.json()
    csrfToken = session.csrf_token
    return { username: session.username, expiresAt: session.expires_at }
  }

  return {
    request,
    clearSession,
    async getSession() {
      return acceptSession(await request('/api/admin/session'))
    },
    async login(username, password) {
      return acceptSession(await request('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      }))
    },
    async logout() {
      await request('/api/admin/logout', { method: 'POST' })
      clearSession()
    }
  }
}
