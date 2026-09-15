<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <div class="brand">⚖️ 律所案件管理系统</div>
      <div class="sub">多团队协作 · 按案件授权 · 全程留痕</div>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="username" placeholder="登录名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" size="large"
                    show-password :prefix-icon="Lock" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
      <el-alert type="info" :closable="false" style="margin-top: 14px">
        <template #title>
          演示账号（密码均为 123456）：admin / zhangwm / chenxd / assistant1
        </template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import api from '../api'
import { auth } from '../auth'

const username = ref('')
const password = ref('')
const loading = ref(false)
const router = useRouter()
const route = useRoute()

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入登录名和密码')
    return
  }
  loading.value = true
  try {
    const res = await api.post('/auth/login/', {
      username: username.value.trim(), password: password.value,
    })
    auth.user = res.data
    ElMessage.success(`欢迎，${res.data.display_name}（${res.data.profile.role_display}）`)
    router.replace(route.query.next || '/')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #001529 0%, #0b3d6b 100%);
}
.login-card { width: 400px; padding: 18px 10px; border-radius: 8px; }
.brand { font-size: 20px; font-weight: 700; text-align: center; color: #001529; }
.sub { color: #999; font-size: 12px; text-align: center; margin: 8px 0 22px; }
</style>
