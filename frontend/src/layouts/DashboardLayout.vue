<template>
  <div class="h-screen w-full flex bg-background relative overflow-hidden text-foreground font-sans">
    <!-- 主内容区（全宽） -->
    <main class="flex-1 flex flex-col min-w-0 relative z-10 overflow-hidden">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
</style>
