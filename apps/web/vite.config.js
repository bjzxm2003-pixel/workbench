import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // 相对路径，方便日后由 FastAPI/任意静态服务托管构建产物
  base: './',
  server: {
    host: true,
    port: 5173,
    proxy: {
      // M1 起 FastAPI 后端提供真实接口
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
