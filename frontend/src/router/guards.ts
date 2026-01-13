import type { Router } from 'vue-router'

/**
 * 注册路由守卫
 */
export function setupRouterGuards(router: Router) {
  // 全局前置守卫
  router.beforeEach((to, _from, next) => {
    const token = localStorage.getItem('token')
    const isAuthenticated = !!token
    
    // 公开路由（不需要登录）
    const publicRoutes = ['/login']
    const isPublicRoute = publicRoutes.includes(to.path)
    
    if (!isAuthenticated && !isPublicRoute) {
      // 未登录且访问需要认证的页面，跳转到登录页
      next({ path: '/login', query: { redirect: to.fullPath } })
    } else if (isAuthenticated && to.path === '/login') {
      // 已登录但访问登录页，跳转到首页
      next('/')
    } else {
      next()
    }
  })
}

