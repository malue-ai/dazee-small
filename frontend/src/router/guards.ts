import type { Router } from 'vue-router'

/**
 * 是否启用认证（可通过环境变量控制）
 * 默认启用
 */
const AUTH_ENABLED = import.meta.env.VITE_AUTH_ENABLED !== 'false'

/**
 * 注册路由守卫
 */
export function setupRouterGuards(router: Router) {
  // 全局前置守卫
  router.beforeEach((to, _from, next) => {
    // 如果禁用认证，直接放行
    if (!AUTH_ENABLED) {
      next()
      return
    }

    const token = localStorage.getItem('token')
    const isAuthenticated = !!token
    
    // 公开路由（不需要登录）
    const publicRoutes = ['/login']
    const isPublicRoute = publicRoutes.includes(to.path)
    
    console.log('🔐 路由守卫:', { 
      path: to.path, 
      isAuthenticated, 
      isPublicRoute,
      token: token ? '存在' : '无'
    })
    
    if (!isAuthenticated && !isPublicRoute) {
      // 未登录且访问需要认证的页面，跳转到登录页
      console.log('🔐 未登录，跳转到登录页')
      next({ path: '/login', query: { redirect: to.fullPath } })
    } else if (isAuthenticated && to.path === '/login') {
      // 已登录但访问登录页，跳转到首页
      console.log('🔐 已登录，跳转到首页')
      next('/')
    } else {
      next()
    }
  })
}

