<template>
  <div class="min-h-screen w-full flex items-center justify-center bg-gray-50 relative overflow-hidden">
    <div class="w-full max-w-md mx-auto p-6 relative z-10">
      <!-- Logo 区域 -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white shadow-lg border border-gray-100 mb-6 transform transition-transform hover:scale-105">
          <Sparkles class="w-8 h-8 text-blue-500" />
        </div>
        <h1 class="text-3xl font-bold tracking-tight text-gray-900">ZenFlux Agent</h1>
        <p class="text-gray-500 mt-2">开发者控制台</p>
      </div>

      <!-- 登录表单 -->
      <div class="bg-white rounded-2xl border border-gray-200 p-8 shadow-lg">
        <form @submit.prevent="handleLogin" class="space-y-5">
          <!-- 用户名 -->
          <div class="space-y-2">
            <label for="username" class="text-sm font-medium text-gray-700 block">
              用户名
            </label>
            <div class="relative">
              <input
                id="username"
                v-model="username"
                type="text"
                placeholder="输入用户名"
                required
                class="w-full px-4 py-3 bg-white border border-gray-200 rounded-xl text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
              />
            </div>
          </div>

          <!-- 密码 -->
          <div class="space-y-2">
            <label for="password" class="text-sm font-medium text-gray-700 block">
              密码
            </label>
            <div class="relative">
              <input
                id="password"
                v-model="password"
                type="password"
                placeholder="输入密码"
                required
                class="w-full px-4 py-3 bg-white border border-gray-200 rounded-xl text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
              />
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMessage" class="p-3 rounded-lg bg-red-50 border border-red-100 text-red-600 text-sm flex items-center gap-2">
            <AlertTriangle class="w-4 h-4 flex-shrink-0" />
            {{ errorMessage }}
          </div>

          <!-- 登录按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-3.5 px-4 bg-gray-900 text-white rounded-xl font-medium shadow-lg shadow-gray-900/10 hover:shadow-gray-900/20 hover:bg-gray-800 disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-200 transform hover:-translate-y-0.5 active:translate-y-0"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <Loader2 class="w-5 h-5 animate-spin" />
              登录中...
            </span>
            <span v-else>登 录</span>
          </button>
        </form>
      </div>

      <!-- 底部提示 -->
      <div class="mt-8 text-center space-y-2">
        <p class="text-xs text-gray-400">
          默认统一密码
        </p>
        <div class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-100 text-gray-500 text-xs font-mono">
          <span>Password:</span>
          <span class="font-bold text-gray-700">zenflux</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Sparkles, AlertTriangle, Loader2 } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    await authStore.login(username.value, password.value)
    
    // 跳转到之前的页面或首页
    const redirect = route.query.redirect as string || '/'
    router.push(redirect)
  } catch (error: unknown) {
    console.error('登录失败:', error)
    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      errorMessage.value = axiosError.response?.data?.detail || '登录失败，请检查密码'
    } else {
      errorMessage.value = '登录失败，请检查密码'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
</style>
