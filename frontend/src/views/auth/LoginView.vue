<template>
  <div class="w-full max-w-md mx-auto p-6">
    <!-- Logo 区域 -->
    <div class="text-center mb-8">
      <div class="text-4xl mb-4">✨</div>
      <h1 class="text-2xl font-semibold text-foreground">ZenFlux Agent</h1>
      <p class="text-muted-foreground mt-2">开发者控制台</p>
    </div>

    <!-- 登录表单 -->
    <div class="bg-card rounded-xl border border-border p-6 shadow-sm">
      <form @submit.prevent="handleLogin" class="space-y-4">
        <!-- 用户名 -->
        <div class="space-y-2">
          <label for="username" class="text-sm font-medium text-foreground">
            用户名
          </label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="输入用户名"
            required
            class="w-full px-3 py-2 border border-input rounded-lg bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
          />
        </div>

        <!-- 密码 -->
        <div class="space-y-2">
          <label for="password" class="text-sm font-medium text-foreground">
            密码
          </label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="输入密码"
            required
            class="w-full px-3 py-2 border border-input rounded-lg bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
          />
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMessage" class="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">
          {{ errorMessage }}
        </div>

        <!-- 登录按钮 -->
        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 px-4 bg-primary text-primary-foreground rounded-lg font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
        >
          <span v-if="loading">登录中...</span>
          <span v-else>登录</span>
        </button>
      </form>
    </div>

    <!-- 底部提示 -->
    <p class="text-center text-sm text-muted-foreground mt-6">
      使用统一密码登录
    </p>
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
      const axiosError = error as { response?: { data?: { message?: string } } }
      errorMessage.value = axiosError.response?.data?.message || '登录失败，请检查密码'
    } else {
      errorMessage.value = '登录失败，请检查密码'
    }
  } finally {
    loading.value = false
  }
}
</script>

