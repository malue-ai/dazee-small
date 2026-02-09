import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initApiBaseUrl } from './api'
import { appLog } from './utils/logger'
import './style.css'
import 'markstream-vue/index.css'
import { enableMermaid } from 'markstream-vue'

// 启用 Mermaid 图表渲染
enableMermaid()

appLog.info('应用启动中...')
appLog.info(`运行环境: ${import.meta.env.MODE}`)
appLog.info(`User-Agent: ${navigator.userAgent.slice(0, 80)}`)

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 初始化 API 基础 URL（Tauri 模式下从 Rust 获取后端地址）
initApiBaseUrl().then(() => {
  app.mount('#app')
  appLog.info('应用挂载完成')
}).catch((err) => {
  appLog.error('API 初始化失败', err)
  app.mount('#app')
})
