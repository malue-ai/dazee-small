<template>
  <div class="h-screen w-full flex bg-background relative overflow-hidden text-foreground font-sans">
    <!-- 左侧导航栏 -->
    <nav class="w-[260px] flex-shrink-0 flex flex-col glass-sidebar relative z-10">
      <!-- Logo 区域 -->
      <div class="h-14 flex items-center gap-2 px-4 pt-2">
        <span class="text-xl">✨</span>
        <span class="font-semibold text-foreground tracking-tight">ZenFlux</span>
      </div>

      <!-- 导航菜单 -->
      <div class="flex-1 py-4 px-3 overflow-y-auto gap-6 flex flex-col">
        <!-- 主导航 -->
        <div class="flex flex-col gap-1">
          <router-link
            v-for="item in mainNavItems"
            :key="item.path"
            :to="item.path"
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors group"
            :class="isActive(item.path) 
              ? 'bg-accent text-accent-foreground' 
              : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
          >
            <component 
              :is="item.icon" 
              class="w-4 h-4"
              :class="isActive(item.path) ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground'"
            />
            <span>{{ item.label }}</span>
            <span 
              v-if="item.badge" 
              class="ml-auto px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground"
            >
              {{ item.badge }}
            </span>
          </router-link>
        </div>

        <!-- 底部导航 -->
        <div class="mt-auto flex flex-col gap-1">
           <!-- 返回聊天 -->
          <router-link
            to="/"
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors group"
          >
            <MessageSquare class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span>返回聊天</span>
          </router-link>
        </div>
      </div>

      <!-- 用户信息 -->
      <div class="border-t border-border pt-3 px-1 pb-4 mx-2">
        <div class="flex items-center justify-between group px-2 py-2 rounded-lg hover:bg-muted cursor-pointer transition-colors">
          <div class="flex items-center gap-3 overflow-hidden">
            <div class="w-6 h-6 rounded-full bg-muted flex items-center justify-center flex-shrink-0 text-[10px] font-bold text-muted-foreground">
              {{ userInitial }}
            </div>
            <span class="text-sm font-medium text-foreground truncate">{{ username }}</span>
          </div>
        </div>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main class="flex-1 flex flex-col min-w-0 relative z-10 overflow-hidden">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { 
  BookOpen, 
  Puzzle, 
  MessageSquare,
  FileText,
  Settings
} from 'lucide-vue-next'
import type { FunctionalComponent } from 'vue'
import type { LucideProps } from 'lucide-vue-next'

// ==================== 类型定义 ====================

interface NavItem {
  path: string
  icon: FunctionalComponent<LucideProps>
  label: string
  badge?: string
}

const route = useRoute()
const router = useRouter()
// ==================== 导航配置 ====================

const mainNavItems: NavItem[] = [
  { path: '/knowledge', icon: BookOpen, label: '知识库' },
  { path: '/skills', icon: Puzzle, label: '技能' },
  { path: '/documentation', icon: FileText, label: '文档' },
  { path: '/settings', icon: Settings, label: '设置' }
]

// ==================== 计算属性 ====================

const username = computed(() => 'local')
const userInitial = computed(() => 'L')

// ==================== 方法 ====================

/**
 * 判断路由是否激活
 */
function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}

</script>

<style scoped>
</style>
