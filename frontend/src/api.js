import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data
    let msg = '请求失败'
    if (typeof detail === 'string') msg = detail
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
