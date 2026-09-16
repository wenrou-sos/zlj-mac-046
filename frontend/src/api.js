import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/api', timeout: 15000 })

function getCookie(name) {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return m ? decodeURIComponent(m[1]) : null
}

// 登录后的写操作需携带 CSRF Token（Session 认证要求）
api.interceptors.request.use((config) => {
  const token = getCookie('csrftoken')
  if (token) config.headers['X-CSRFToken'] = token
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data
    let msg = '请求失败'
    if (err.response?.status === 401 || err.response?.status === 403) {
      msg = typeof detail === 'object' && detail?.detail
        ? detail.detail
        : '请先登录后再执行该操作'
    } else if (typeof detail === 'string') msg = detail
    else if (detail?.detail) msg = detail.detail
    else if (detail) {
      const first = Object.values(detail)[0]
      msg = Array.isArray(first) ? first[0] : String(first)
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default api
