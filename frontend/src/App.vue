<template>
  <component :is="layout">
    <router-view />
  </component>
  <!-- 全局调试面板（所有页面可见） -->
  <DebugPanel />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import DebugPanel from '@/components/common/DebugPanel.vue'

const route = useRoute()

const layout = computed(() => {
  const layoutName = route.meta.layout as string | undefined
  if (layoutName === 'dashboard') {
    return DashboardLayout
  }
  return DefaultLayout
})
</script>
