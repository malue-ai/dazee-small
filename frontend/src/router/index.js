import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'

const routes = [
  {
    path: '/',
    name: 'chat',
    component: ChatView
  },
  {
    path: '/c/:conversationId',
    name: 'conversation',
    component: ChatView
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: KnowledgeView
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router

