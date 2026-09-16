<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">⚖️ 律所案件管理</div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#001529"
        text-color="#a6adb4"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/">工作台</el-menu-item>
        <el-menu-item index="/cases">案件管理</el-menu-item>
        <el-menu-item index="/parties">当事人管理</el-menu-item>
        <el-menu-item index="/lawyers">律师管理</el-menu-item>
        <el-menu-item index="/conflict">利益冲突检查</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ $route.meta.title || '律所案件管理系统' }}</span>
        <div class="header-right">
          <span class="today">{{ today }}</span>
          <template v-if="auth.user">
            <el-tag size="small" :type="auth.user.is_staff ? 'danger' : 'success'" effect="plain">
              {{ auth.user.name }}{{ auth.user.is_staff ? '（管理员）' : '' }}
            </el-tag>
            <el-button link type="primary" @click="doLogout">退出</el-button>
          </template>
          <el-button v-else type="primary" size="small" @click="loginDialog = true">登录</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 登录对话框 -->
    <el-dialog v-model="loginDialog" title="登录" width="380px">
      <el-form label-width="70px" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="loginForm.username" placeholder="如 zhangwm / admin" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="loginForm.password" type="password" show-password
            @keyup.enter="doLogin" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loginDialog = false">取消</el-button>
        <el-button type="primary" :loading="loginLoading" @click="doLogin">登录</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { auth, fetchMe, login, logout } from './auth'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/cases')) return '/cases'
  return route.path
})
const today = new Date().toLocaleDateString('zh-CN', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
})

const loginDialog = ref(false)
const loginLoading = ref(false)
const loginForm = reactive({ username: '', password: '' })

async function doLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loginLoading.value = true
  try {
    await login(loginForm.username, loginForm.password)
    ElMessage.success(`欢迎，${auth.user.name}`)
    loginDialog.value = false
    loginForm.username = ''
    loginForm.password = ''
  } catch (e) {
    // 拦截器已提示
  } finally {
    loginLoading.value = false
  }
}

async function doLogout() {
  await logout()
  ElMessage.success('已退出登录')
}

onMounted(fetchMe)
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
.layout { height: 100%; }
.aside { background: #001529; }
.logo {
  color: #fff; font-size: 17px; font-weight: 600;
  padding: 18px 16px; letter-spacing: 1px;
}
.aside .el-menu { border-right: none; }
.header {
  background: #fff; border-bottom: 1px solid #e8e8e8;
  display: flex; align-items: center; justify-content: space-between;
}
.header-right { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 16px; font-weight: 600; }
.today { color: #888; font-size: 13px; }
.main { background: #f0f2f5; }
</style>
