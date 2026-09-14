import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { title: '工作台' } },
  { path: '/cases', name: 'cases', component: () => import('./views/CaseList.vue'), meta: { title: '案件管理' } },
  { path: '/cases/:id', name: 'case-detail', component: () => import('./views/CaseDetail.vue'), meta: { title: '案件详情' } },
  { path: '/parties', name: 'parties', component: () => import('./views/PartyList.vue'), meta: { title: '当事人管理' } },
  { path: '/lawyers', name: 'lawyers', component: () => import('./views/LawyerList.vue'), meta: { title: '律师管理' } },
  { path: '/conflict', name: 'conflict', component: () => import('./views/ConflictCheck.vue'), meta: { title: '利益冲突检查' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
