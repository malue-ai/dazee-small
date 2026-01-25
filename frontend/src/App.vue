<template>
  <component :is="layout">
    <router-view />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import AuthLayout from '@/layouts/AuthLayout.vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'

const route = useRoute()

// 根据路由 meta.layout 选择布局组件
const layout = computed(() => {
  const layoutName = route.meta.layout as string | undefined
  if (layoutName === 'auth') {
    return AuthLayout
  }
  if (layoutName === 'dashboard') {
    return DashboardLayout
  }
  return DefaultLayout
})
</script>
