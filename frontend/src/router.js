import { createRouter, createWebHistory } from 'vue-router'
import { auth, loadMe } from './auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { title: '登录', public: true } },
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { title: '工作台' } },
  { path: '/cases', name: 'cases', component: () => import('./views/CaseList.vue'), meta: { title: '案件管理' } },
  { path: '/cases/:id', name: 'case-detail', component: () => import('./views/CaseDetail.vue'), meta: { title: '案件详情' } },
  { path: '/parties', name: 'parties', component: () => import('./views/PartyList.vue'), meta: { title: '当事人管理' } },
  { path: '/lawyers', name: 'lawyers', component: () => import('./views/LawyerList.vue'), meta: { title: '律师管理' } },
  { path: '/conflict', name: 'conflict', component: () => import('./views/ConflictCheck.vue'), meta: { title: '利益冲突检查' } },
  { path: '/accounts', name: 'accounts', component: () => import('./views/AccountList.vue'), meta: { title: '账号权限', adminOnly: true } },
  { path: '/audit', name: 'audit', component: () => import('./views/AuditLogs.vue'), meta: { title: '审计日志', adminOnly: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (!auth.loaded) await loadMe()
  if (!to.meta.public && !auth.user) {
    return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  }
  if (to.name === 'login' && auth.user) return { name: 'dashboard' }
  if (to.meta.adminOnly && !auth.user?.is_admin) return { name: 'dashboard' }
  return true
})

export default router
