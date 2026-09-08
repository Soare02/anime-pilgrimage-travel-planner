<template>
  <el-dialog
    v-model="store.settingsOpen"
    title="你的 AI 旅伴"
    width="460px"
    append-to-body
    class="ai-settings-dialog"
  >
    <p class="settings-intro">选择熟悉的 AI 服务，为收藏的风景安排一段旅程。</p>
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="规划方式">
        <el-radio-group v-model="draft.scheme" class="scheme-options">
          <el-radio-button value="cloud">云端服务</el-radio-button>
          <el-radio-button value="local">本地模型</el-radio-button>
          <el-radio-button value="agent">智能体</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="接口地址">
        <el-input
          v-model="draft[draft.scheme].url"
          placeholder="https://…/chat/completions"
          :disabled="draft.scheme === 'agent'"
        />
      </el-form-item>
      <template v-if="draft.scheme !== 'agent'">
        <el-form-item label="API Key"
          ><el-input
            v-model="draft[draft.scheme].apiKey"
            type="password"
            show-password
            autocomplete="off"
            placeholder="填写服务密钥"
        /></el-form-item>
        <el-form-item label="模型名称"
          ><el-input
            v-model="draft[draft.scheme].model"
            placeholder="填写模型名称"
        /></el-form-item>
      </template>
      <p v-else class="settings-note">
        智能体会检索目的地信息、天气与交通。使用前请启动本地 Python 服务，并在
        .env 中配置模型与搜索密钥。
      </p>
    </el-form>
    <template #footer>
      <el-button @click="store.settingsOpen = false">取消</el-button>
      <el-button type="primary" @click="save">保存设置</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const draft = reactive(JSON.parse(JSON.stringify(store.aiConfig)))
watch(
  () => store.settingsOpen,
  (open) => {
    if (open) Object.assign(draft, JSON.parse(JSON.stringify(store.aiConfig)))
  }
)
function save() {
  store.aiConfig = JSON.parse(JSON.stringify(draft))
  store.saveAiConfig()
  store.settingsOpen = false
  ElMessage.success('AI 旅伴设置已保存')
}
</script>

<style scoped>
.settings-intro {
  margin: -4px 0 24px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.scheme-options {
  display: flex;
  width: 100%;
}
.scheme-options :deep(.el-radio-button) {
  flex: 1;
}
.scheme-options :deep(.el-radio-button__inner) {
  width: 100%;
  padding: 12px 16px;
}
.settings-note {
  padding: 16px;
  border-radius: 12px;
  background: var(--primary-soft);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.8;
}
</style>
