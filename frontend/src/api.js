import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/api', timeout: 15000 })

// 与后端 SessionAuthentication 对齐：从 csrftoken Cookie 取令牌放入 X-CSRFToken 头
function getCookie(name) {
  const m = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`))
  return m ? m[2] : null
}

api.defaults.xsrfCookieName = 'csrftoken'
api.defaults.xsrfHeaderName = 'X-CSRFToken'
api.defaults.withCredentials = true

let redirecting = false

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    // 会话失效：统一跳转登录页（认证类接口除外）
    if (status === 401 && !err.config?.url?.includes('/auth/')) {
      if (!redirecting && !location.pathname.endsWith('/login')) {
        redirecting = true
        ElMessage.warning('登录已失效，请重新登录')
        location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search)
      }
      return Promise.reject(err)
    }
    const detail = err.response?.data
    let msg = '请求失败'
    if (typeof detail === 'string') msg = detail
    else if (detail?.detail) msg = detail.detail
    else if (detail) {
      const first = Object.values(detail)[0]
      msg = Array.isArray(first) ? first[0] : String(first)
    }
    if (status !== 401) ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export { getCookie }
export default api
