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
  </template>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import DebugPanel from '@/components/common/DebugPanel.vue'
import SplashScreen from '@/components/common/SplashScreen.vue'

const route = useRoute()
const router = useRouter()

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

  // 首次使用：跳转引导页
  const onboardingDone = localStorage.getItem('zenflux_onboarding_done')
  if (!onboardingDone && route.name !== 'onboarding') {
    router.replace('/onboarding')
  }
}
</script>
