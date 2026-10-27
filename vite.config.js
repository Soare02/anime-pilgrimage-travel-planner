import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  build: {
    rollupOptions: {
      input: {
        app: fileURLToPath(new URL('./index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin/index.html', import.meta.url)),
      },
    },
  },
  server: {
    proxy: {
      '/anitabi-data': {
        target: 'https://www.anitabi.cn',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/anitabi-data/, '/d'),
        proxyTimeout: 20000,
      },
      '/ark': {
        target: 'https://ark.cn-beijing.volces.com/api/v3',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ark/, ''),
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/bgm': {
        target: 'https://v2-anitabi.magiconch.com/api/bgm',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/bgm/, ''),
        proxyTimeout: 15000,
      },
    },
  },
})
