import { reactive, watch } from 'vue'

// 全局"当前操作律师"身份：用于申请人/复核人隔离与全程留痕
const STORAGE_KEY = 'current_lawyer_id'

export const identity = reactive({
  lawyerId: Number(localStorage.getItem(STORAGE_KEY)) || null,
  lawyers: [],
})

watch(() => identity.lawyerId, (val) => {
  if (val) localStorage.setItem(STORAGE_KEY, String(val))
  else localStorage.removeItem(STORAGE_KEY)
})

export function currentLawyer() {
  return identity.lawyers.find((l) => l.id === identity.lawyerId) || null
}

export async function loadLawyers() {
  const { default: api } = await import('./api')
  const res = await api.get('/lawyers/')
  identity.lawyers = res.data
  // 清除失效选择
  if (identity.lawyerId && !identity.lawyers.some((l) => l.id === identity.lawyerId)) {
    identity.lawyerId = null
  }
  return identity.lawyers
}
