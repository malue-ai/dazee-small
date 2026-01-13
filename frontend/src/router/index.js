import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import AgentListView from '../views/AgentListView.vue'
import AgentCreateView from '../views/AgentCreateView.vue'

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
  },
  {
    path: '/agents',
    name: 'agents',
    component: AgentListView
  },
  {
    path: '/agents/create',
    name: 'agent-create',
    component: AgentCreateView
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router

