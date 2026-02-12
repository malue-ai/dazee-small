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

  // ==================== Agent（项目）对话 ====================
  {
    path: '/agent/:agentId',
    name: 'agent',
    component: () => import('@/views/chat/ChatView.vue')
  },
  {
    path: '/agent/:agentId/c/:conversationId',
    name: 'agent-conversation',
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
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('@/views/tasks/ScheduledTasksView.vue'),
    meta: { layout: 'dashboard' }
  },
  // ==================== 新建项目 ====================
  {
    path: '/create-project',
    name: 'create-project',
    component: () => import('@/views/project/CreateProjectView.vue'),
    meta: { layout: 'none' }
  },
  // ==================== 编辑项目 ====================
  {
    path: '/edit-project/:agentId',
    name: 'edit-project',
    component: () => import('@/views/project/CreateProjectView.vue'),
    meta: { layout: 'none' }
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

