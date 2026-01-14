<template>
  <div class="min-h-screen w-full flex items-center justify-center bg-gray-50 relative overflow-hidden">
    <!-- 背景装饰 -->
    <div class="absolute inset-0 z-0 opacity-30">
      <div class="absolute top-0 left-0 w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob"></div>
      <div class="absolute top-0 right-0 w-96 h-96 bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-2000"></div>
      <div class="absolute -bottom-8 left-20 w-96 h-96 bg-pink-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-4000"></div>
    </div>

    <div class="w-full max-w-md mx-auto p-6 relative z-10">
      <!-- Logo 区域 -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white shadow-lg mb-6 transform transition-transform hover:scale-105">
          <span class="text-4xl">✨</span>
        </div>
        <h1 class="text-3xl font-bold tracking-tight text-gray-900">ZenFlux Agent</h1>
        <p class="text-gray-500 mt-2">开发者控制台</p>
      </div>

      <!-- 登录表单 -->
      <div class="bg-white/80 backdrop-blur-xl rounded-2xl border border-white/20 p-8 shadow-xl">
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
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
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
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
              />
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMessage" class="p-3 rounded-lg bg-red-50 text-red-600 text-sm flex items-center gap-2 animate-in fade-in slide-in-from-top-2">
            <span class="text-lg">⚠️</span>
            {{ errorMessage }}
          </div>

          <!-- 登录按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-3.5 px-4 bg-gray-900 text-white rounded-xl font-medium shadow-lg shadow-gray-900/10 hover:shadow-gray-900/20 hover:bg-gray-800 disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-200 transform hover:-translate-y-0.5 active:translate-y-0"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
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
        <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-100 text-gray-500 text-xs font-mono">
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
@keyframes blob {
  0% {
    transform: translate(0px, 0px) scale(1);
  }
  33% {
    transform: translate(30px, -50px) scale(1.1);
  }
  66% {
    transform: translate(-20px, 20px) scale(0.9);
  }
  100% {
    transform: translate(0px, 0px) scale(1);
  }
}
.animate-blob {
  animation: blob 7s infinite;
}
.animation-delay-2000 {
  animation-delay: 2s;
}
.animation-delay-4000 {
  animation-delay: 4s;
}
</style>
