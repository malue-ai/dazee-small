import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/**
 * 认证相关组合式函数
 */
export function useAuth() {
  const router = useRouter()
  const authStore = useAuthStore()

  const isAuthenticated = computed(() => authStore.isAuthenticated)
  const user = computed(() => authStore.user)
  const loading = computed(() => authStore.loading)

  /**
   * 登录
   */
  async function login(username: string, password: string) {
    try {
      await authStore.login(username, password)
      router.push('/')
    } catch (error) {
      console.error('登录失败:', error)
      throw error
    }
  }

  /**
   * 登出
   */
  function logout() {
    authStore.logout()
    router.push('/login')
  }

  /**
   * 检查是否已登录，未登录则跳转到登录页
   */
  function requireAuth() {
    if (!isAuthenticated.value) {
      router.push('/login')
      return false
    }
    return true
  }

  return {
    isAuthenticated,
    user,
    loading,
    login,
    logout,
    requireAuth
  }
}

