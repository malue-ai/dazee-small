<template>
  <!-- Splash 加载画面 -->
  <SplashScreen v-if="showSplash" @done="onSplashDone" />

  <!-- 主应用 -->
  <template v-if="appReady">
    <component :is="layout" v-if="layout">
      <router-view />
    </component>
    <router-view v-else />
    <!-- 全局调试面板（仅开发环境可见，打包时自动移除） -->
    <DebugPanel v-if="isDev" />
    <!-- 全局引导浮层 -->
    <GuideOverlay />
    <!-- 全局通知中心（Agent 创建进度、聊天消息提醒等） -->
    <NotificationCenter />
    <!-- 自动更新弹窗 -->
    <UpdateDialog
      :phase="updater.phase.value"
      :version="updater.newVersion.value"
      :changelog="updater.changelog.value"
      :progress="updater.downloadProgress.value"
      :error="updater.errorMessage.value"
      @confirm="updater.downloadAndInstall"
      @dismiss="updater.dismiss"
    />
  </template>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import DebugPanel from '@/components/common/DebugPanel.vue'
import SplashScreen from '@/components/common/SplashScreen.vue'
import GuideOverlay from '@/components/common/GuideOverlay.vue'
import NotificationCenter from '@/components/common/NotificationCenter.vue'
import UpdateDialog from '@/components/common/UpdateDialog.vue'
import { useConnectionStore } from '@/stores/connection'
import { useAutoUpdate } from '@/composables/useAutoUpdate'

const route = useRoute()
const connectionStore = useConnectionStore()

const isDev = import.meta.env.DEV
const updater = useAutoUpdate()

const showSplash = ref(true)
const appReady = ref(false)

const layout = computed(() => {
  const layoutName = route.meta.layout as string | undefined
  if (layoutName === 'none') return null
  if (layoutName === 'dashboard') return DashboardLayout
  return DefaultLayout
})

function onSplashDone() {
  showSplash.value = false
  appReady.value = true

  // 建立全局 WebSocket 连接，用于接收定时任务等广播通知
  connectionStore.initNotificationChannel()

  // 启动后延迟 3 秒静默检查更新，仅在打包模式下运行
  if (!isDev) {
    setTimeout(() => updater.checkForUpdates(true), 3000)
  }
}
</script>
