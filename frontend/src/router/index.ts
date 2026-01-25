import { createRouter, createWebHistory } from 'vue-router'
import { setupRouterGuards } from './guards'

// 路由配置
const routes = [
  // ==================== 认证页面 ====================
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { layout: 'auth' }
  },

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
    path: '/agents',
    name: 'agents',
    component: () => import('@/views/agent/AgentListView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/agents/create',
    name: 'agent-create',
    component: () => import('@/views/agent/AgentCreateView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/agents/:agentId',
    name: 'agent-detail',
    component: () => import('@/views/agent/AgentDetailView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/skills',
    name: 'skills',
    component: () => import('@/views/skills/SkillsView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/tutorial',
    name: 'tutorial',
    component: () => import('@/views/tutorial/TutorialView.vue'),
    meta: { layout: 'dashboard' }
  },
  {
    path: '/tutorial/:chapterId',
    name: 'tutorial-chapter',
    component: () => import('@/views/tutorial/TutorialView.vue'),
    meta: { layout: 'dashboard' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 注册路由守卫
setupRouterGuards(router)

export default router

