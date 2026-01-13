import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import * as authApi from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  // 状态
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(
    localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')!) : null
  )
  const loading = ref(false)

  // 计算属性
  const isAuthenticated = computed(() => !!token.value)
  const username = computed(() => user.value?.username || '')

  // 登录
  async function login(loginUsername: string, password: string) {
    loading.value = true
    try {
      const response = await authApi.login({ username: loginUsername, password })
      
      // 保存 token 和用户信息
      token.value = response.token
      user.value = response.user
      
      localStorage.setItem('token', response.token)
      localStorage.setItem('user', JSON.stringify(response.user))
      
      return response
    } finally {
      loading.value = false
    }
  }

  // 登出
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  // 初始化用户 ID（兼容旧逻辑）
  function initUserId(): string {
    if (user.value?.id) {
      return user.value.id
    }
    // 如果没有登录，使用本地生成的 ID
    let userId = localStorage.getItem('userId')
    if (!userId) {
      userId = 'user_' + Date.now()
      localStorage.setItem('userId', userId)
    }
    return userId
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    username,
    login,
    logout,
    initUserId
  }
})

