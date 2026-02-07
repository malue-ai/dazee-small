<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 -->
    <div class="h-16 flex items-center justify-between px-6 border-b border-border bg-white sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-foreground">
          <BookOpen class="w-6 h-6 text-primary" />
          知识库
        </h1>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50">
      <div class="w-20 h-20 bg-muted rounded-3xl flex items-center justify-center mb-4 border border-border">
        <BookOpen class="w-10 h-10 opacity-30" />
      </div>
      <p class="text-sm font-medium text-muted-foreground">知识库功能开发中</p>
      <p class="text-xs mt-1 text-muted-foreground/50">敬请期待</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BookOpen } from 'lucide-vue-next'
</script>
