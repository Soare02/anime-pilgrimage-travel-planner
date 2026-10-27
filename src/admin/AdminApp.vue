<template>
  <component
    :is="adminPanel"
    v-if="session && adminPanel"
    :username="session.username"
    :request="api.request"
    :logging-out="loggingOut"
    @logout="logout"
  />
  <main v-else class="admin-gateway">
    <section class="login-card" aria-labelledby="admin-heading">
      <span class="login-badge">巡礼手帖 · 管理后台</span>
      <h1 id="admin-heading">巡礼数据中心</h1>
      <p class="login-description">登录后管理知识库、审核资料与查看运行追踪。</p>

      <p v-if="checking" class="gateway-status" role="status">正在验证管理员身份…</p>
      <template v-else-if="session">
        <p class="gateway-status" :role="panelError ? 'alert' : 'status'">
          {{ panelError || '正在加载管理页面…' }}
        </p>
        <div class="gateway-actions">
          <button v-if="panelError" class="primary-button" @click="loadAdminPanel">重新加载</button>
          <button class="glass-action-btn" :disabled="loggingOut" @click="logout">退出登录</button>
        </div>
      </template>
      <form v-else class="login-form" @submit.prevent="login">
        <label for="admin-username">管理员账号</label>
        <input
          id="admin-username"
          v-model="username"
          name="username"
          autocomplete="username"
          maxlength="128"
          required
          :disabled="signingIn"
        />
        <label for="admin-password">密码</label>
        <input
          id="admin-password"
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          maxlength="1024"
          required
          :disabled="signingIn"
        />
        <p v-if="message" class="login-message" role="alert">{{ message }}</p>
        <button class="primary-button login-submit" type="submit" :disabled="signingIn">
          {{ signingIn ? '正在登录…' : '登录管理后台' }}
        </button>
      </form>

      <a class="return-link" href="/">返回巡礼地图</a>
    </section>
  </main>
</template>

<script setup>
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createAdminApi } from './api'

const session = ref(null)
const checking = ref(true)
const signingIn = ref(false)
const loggingOut = ref(false)
const username = ref('')
const password = ref('')
const message = ref('')
const adminPanel = shallowRef(null)
const panelError = ref('')
let panelLoading = false
let expiryTimer

const api = createAdminApi({ onUnauthorized: () => clearSession('登录已失效，请重新登录。') })

function clearSession(reason = '') {
  session.value = null
  api.clearSession()
  password.value = ''
  message.value = reason
  clearTimeout(expiryTimer)
  // Close any pending destructive confirmation when the session ends.
  ElMessageBox.close()
}

function acceptSession(value) {
  session.value = value
  message.value = ''
  clearTimeout(expiryTimer)
  expiryTimer = setTimeout(() => clearSession('登录已过期，请重新登录。'), Math.max(0, value.expiresAt * 1000 - Date.now()))
  loadAdminPanel()
}

async function loadAdminPanel() {
  if (adminPanel.value || panelLoading) return
  panelLoading = true
  panelError.value = ''
  let timeout
  try {
    const module = await Promise.race([
      import('../components/RagAdminPanel.vue'),
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('管理页面加载超时，请重试。')), 20000)
      })
    ])
    adminPanel.value = module.default
  } catch {
    panelError.value = '管理页面加载失败，请检查连接后重新加载。'
  } finally {
    clearTimeout(timeout)
    panelLoading = false
  }
}

async function restoreSession() {
  try {
    acceptSession(await api.getSession())
  } catch (error) {
    clearSession(error.status === 401 ? '' : (error.message || '无法连接管理服务。'))
  } finally {
    checking.value = false
  }
}

async function login() {
  if (signingIn.value) return
  signingIn.value = true
  message.value = ''
  try {
    acceptSession(await api.login(username.value.trim(), password.value))
  } catch (error) {
    message.value = error.message || '无法连接管理服务，请稍后重试。'
  } finally {
    password.value = ''
    signingIn.value = false
  }
}

async function logout() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await api.logout()
    clearSession()
  } catch (error) {
    if (error.status !== 401) ElMessage.error(error.message || '退出失败，请稍后重试。')
  } finally {
    loggingOut.value = false
  }
}

// Validate again after returning from browser history; never restore cached data
// without checking the server-side session.
function handlePageShow(event) {
  if (event.persisted) {
    clearSession()
    checking.value = true
    restoreSession()
  }
}

onMounted(() => {
  restoreSession()
  window.addEventListener('pageshow', handlePageShow)
})
onUnmounted(() => {
  clearTimeout(expiryTimer)
  window.removeEventListener('pageshow', handlePageShow)
})
</script>

<style scoped>
.admin-gateway {
  height: 100dvh;
  overflow-y: auto;
  display: grid;
  place-items: center;
  padding: 28px 20px;
}
.login-card {
  width: 100%;
  max-width: 440px;
  padding: 36px;
  border: 1px solid var(--glass-border);
  border-radius: 24px;
  background: var(--glass-bg-strong);
  box-shadow: var(--glass-shadow);
  backdrop-filter: var(--glass-blur);
}
.login-badge { color: var(--primary-color); font-size: 12px; font-weight: 600; }
h1 { margin: 14px 0 10px; font-size: 26px; }
.login-description, .gateway-status { color: var(--text-secondary); line-height: 1.7; }
.gateway-status { margin: 28px 0; }
.login-form { display: flex; flex-direction: column; margin-top: 28px; }
.login-form label { margin-bottom: 8px; font-weight: 500; }
.login-form input {
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  margin-bottom: 20px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-color);
  background: var(--surface-solid);
}
.login-submit { min-height: 44px; }
.login-message { color: #b91c1c; line-height: 1.7; margin-bottom: 20px; overflow-wrap: anywhere; }
.gateway-actions { display: flex; flex-wrap: wrap; gap: 12px; }
.return-link { display: inline-block; margin-top: 24px; color: var(--text-secondary); text-decoration: none; }
.return-link:hover { color: var(--primary-color); }
@media (max-width: 480px) { .login-card { padding: 28px 24px; } }
</style>
