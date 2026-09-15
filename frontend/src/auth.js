import { reactive } from 'vue'
import api from './api'

// 全局登录态（在路由守卫与各页面共享）
export const auth = reactive({
  user: null,
  loaded: false,
})

export async function loadMe() {
  try {
    const res = await api.get('/auth/me/')
    auth.user = res.data
  } catch {
    auth.user = null
  } finally {
    auth.loaded = true
  }
  return auth.user
}

export async function login(username, password) {
  const res = await api.post('/auth/login/', { username, password })
  auth.user = res.data
  return res.data
}

export async function logout() {
  try {
    await api.post('/auth/logout/')
  } finally {
    auth.user = null
  }
}

const ROLE_LABEL = { admin: '管理员', lead: '主办律师', assist: '协办律师', reader: '只读助理' }
export const roleLabel = (r) => ROLE_LABEL[r] || r

// 案件级可编辑：管理员或案件授权 can_edit
export function canEditCase(c) {
  if (!auth.user) return false
  if (auth.user.is_admin) return true
  return !!c?.my_access?.can_edit
}
