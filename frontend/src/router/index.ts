import { createRouter, createWebHistory } from 'vue-router'
import { setupRouterGuards } from './guards'

// 路由配置
const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { layout: 'auth' }
  },
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
  {
    path: '/agents',
    name: 'agents',
    component: () => import('@/views/agent/AgentListView.vue')
  },
  {
    path: '/agents/create',
    name: 'agent-create',
    component: () => import('@/views/agent/AgentCreateView.vue')
  },
  {
    path: '/agents/:agentId',
    name: 'agent-detail',
    component: () => import('@/views/agent/AgentDetailView.vue')
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('@/views/knowledge/KnowledgeView.vue')
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 注册路由守卫
setupRouterGuards(router)

export default router

