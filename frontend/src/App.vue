<template>
  <component :is="layout">
    <router-view />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'

const route = useRoute()

const layout = computed(() => {
  const layoutName = route.meta.layout as string | undefined
  if (layoutName === 'dashboard') {
    return DashboardLayout
  }
  return DefaultLayout
})
</script>
