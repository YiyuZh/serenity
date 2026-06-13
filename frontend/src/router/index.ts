import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api/client'
import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import PostDetailView from '../views/PostDetailView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: DashboardView },
    { path: '/posts/:id', component: PostDetailView }
  ]
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !getToken()) return '/login'
  if (to.path === '/login' && getToken()) return '/'
  return true
})
