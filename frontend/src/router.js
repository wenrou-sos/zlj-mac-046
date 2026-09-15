import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { title: '工作台' } },
  { path: '/cases', name: 'cases', component: () => import('./views/CaseList.vue'), meta: { title: '案件管理' } },
  { path: '/cases/:id', name: 'case-detail', component: () => import('./views/CaseDetail.vue'), meta: { title: '案件详情' } },
  { path: '/parties', name: 'parties', component: () => import('./views/PartyList.vue'), meta: { title: '当事人管理' } },
  { path: '/lawyers', name: 'lawyers', component: () => import('./views/LawyerList.vue'), meta: { title: '律师管理' } },
  { path: '/conflict', name: 'conflict', component: () => import('./views/ConflictCheck.vue'), meta: { title: '利益冲突检查' } },
  { path: '/conflict-reviews', name: 'conflict-reviews', component: () => import('./views/ConflictReviews.vue'), meta: { title: '冲突复核单' } },
  { path: '/conflict-reviews/:id', name: 'conflict-review-detail', component: () => import('./views/ConflictReviewDetail.vue'), meta: { title: '复核单详情' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
