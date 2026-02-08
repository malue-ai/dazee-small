<template>
  <!-- Splash 加载画面 -->
  <SplashScreen v-if="showSplash" @done="onSplashDone" />

  <!-- 主应用 -->
  <template v-if="appReady">
    <component :is="layout" v-if="layout">
      <router-view />
    </component>
    <router-view v-else />
    <!-- 全局调试面板（所有页面可见） -->
    <DebugPanel />
    <!-- 全局引导浮层 -->
    <GuideOverlay />
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

const route = useRoute()

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
  // 旧引导页已弃用，改为 ChatView 中的交互式引导
}
</script>
