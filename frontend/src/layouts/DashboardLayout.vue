<template>
  <div class="h-screen w-full flex bg-white relative overflow-hidden text-gray-900 font-sans">
    <!-- 左侧导航栏 -->
    <nav class="w-[260px] flex-shrink-0 flex flex-col border-r border-gray-100 bg-gray-50 relative z-10">
      <!-- Logo 区域 -->
      <div class="h-14 flex items-center gap-2 px-4 pt-2">
        <span class="text-xl">✨</span>
        <span class="font-semibold text-gray-700 tracking-tight">ZenFlux</span>
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
              ? 'bg-gray-200/80 text-gray-900' 
              : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
          >
            <component 
              :is="item.icon" 
              class="w-4 h-4"
              :class="isActive(item.path) ? 'text-gray-800' : 'text-gray-500 group-hover:text-gray-800'"
            />
            <span>{{ item.label }}</span>
            <span 
              v-if="item.badge" 
              class="ml-auto px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-200 text-gray-600"
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
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-200/50 hover:text-gray-900 transition-colors group"
          >
            <MessageSquare class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
            <span>返回聊天</span>
          </router-link>
        </div>
      </div>

      <!-- 用户信息 -->
      <div class="border-t border-gray-200/50 pt-3 px-1 pb-4 mx-2">
        <div class="flex items-center justify-between group px-2 py-2 rounded-lg hover:bg-gray-200/50 cursor-pointer transition-colors">
          <div class="flex items-center gap-3 overflow-hidden">
            <div class="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0 text-[10px] font-bold text-gray-600">
              {{ userInitial }}
            </div>
            <span class="text-sm font-medium text-gray-700 truncate">{{ username }}</span>
          </div>
          
          <button 
            v-if="isAuthenticated"
            @click.stop="handleLogout"
            class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-300/50 rounded-md transition-colors"
            title="退出登录"
          >
            <LogOut class="w-4 h-4" />
          </button>
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
import { useAuthStore } from '@/stores/auth'
import { 
  BookOpen, 
  Bot, 
  Puzzle, 
  GraduationCap, 
  MessageSquare,
  LogOut 
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// ==================== 导航配置 ====================

const mainNavItems = [
  { path: '/knowledge', icon: BookOpen, label: '知识库' },
  { path: '/agents', icon: Bot, label: '智能体' },
  { path: '/skills', icon: Puzzle, label: '技能' },
  { path: '/tutorial', icon: GraduationCap, label: '教程', badge: 'New' }
]

// ==================== 计算属性 ====================

const username = computed(() => authStore.username || '访客')
const isAuthenticated = computed(() => authStore.isAuthenticated)
const userInitial = computed(() => username.value.charAt(0).toUpperCase())

// ==================== 方法 ====================

/**
 * 判断路由是否激活
 */
function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}

/**
 * 登出
 */
function handleLogout(): void {
  if (confirm('确定要退出登录吗？')) {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
</style>
