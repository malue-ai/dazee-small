import { createRouter, createWebHistory } from 'vue-router'

// 路由配置
const routes = [
  // ==================== 聊天页面（默认布局） ====================
  {
    path: '/',
    name: 'chat',
    component: () => import('@/views/chat/ChatView.vue')
  },
  {
    path: '/c/:conversationId',
    name: 'conversation',
    component: () => import('@/views/chat/ChatView.vue')
  },

  // ==================== 管理后台（Dashboard 布局） ====================
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('@/views/knowledge/KnowledgeView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/skills',
    name: 'skills',
    component: () => import('@/views/skills/SkillsView.vue'),
    meta: { layout: 'dashboard' }
  },
  // ==================== 文档浏览 ====================
  {
    path: '/documentation',
    name: 'documentation',
    component: () => import('@/views/docs/DocsView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/documentation/:docPath(.*)',
    name: 'documentation-detail',
    component: () => import('@/views/docs/DocsView.vue'),
    meta: { layout: 'dashboard' }
  },

  // ==================== 实时语音 ====================
  {
    path: '/realtime',
    name: 'realtime',
    component: () => import('@/views/realtime/RealtimeView.vue'),
    meta: { layout: 'none' }  // 独立布局
  },

  // ==================== 设置页面 ====================
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/settings/SettingsView.vue'),
    meta: { layout: 'none' }
  },

  // ==================== 引导页（首次使用） ====================
  {
    path: '/onboarding',
    name: 'onboarding',
    component: () => import('@/views/onboarding/OnboardingView.vue'),
    meta: { layout: 'none' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router

