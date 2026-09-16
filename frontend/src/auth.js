import { reactive } from 'vue'
import api from './api'

/** 全局登录状态：auth.user 为 null 表示匿名 */
export const auth = reactive({ user: null, loaded: false })

export async function fetchMe() {
  try {
    const res = await api.get('/auth/me/')
    auth.user = res.data.user
  } finally {
    auth.loaded = true
  }
}

export async function login(username, password) {
  const res = await api.post('/auth/login/', { username, password })
  auth.user = res.data.user
}

export async function logout() {
  await api.post('/auth/logout/')
  auth.user = null
}
