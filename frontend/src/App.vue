<template>
  <el-container class="layout" v-if="auth.user">
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
        <el-menu-item v-if="auth.user.is_admin" index="/accounts">账号权限</el-menu-item>
        <el-menu-item v-if="auth.user.is_admin" index="/audit">审计日志</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ $route.meta.title || '律所案件管理系统' }}</span>
        <el-dropdown @command="onCommand">
          <span class="user-area">
            <el-tag size="small" :type="auth.user.is_admin ? 'danger' : 'info'" effect="dark">
              {{ auth.user.profile.role_display }}
            </el-tag>
            <span class="user-name">{{ auth.user.display_name }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { auth, logout } from './auth'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => {
  if (route.path.startsWith('/cases')) return '/cases'
  return route.path
})

async function onCommand(cmd) {
  if (cmd === 'logout') {
    try {
      await ElMessageBox.confirm('确定退出登录？', '提示', { type: 'warning' })
    } catch {
      return
    }
    await logout()
    router.replace('/login')
  }
}
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
.page-title { font-size: 16px; font-weight: 600; }
.user-area { display: flex; align-items: center; gap: 8px; cursor: pointer; outline: none; }
.user-name { font-size: 14px; color: #333; }
.main { background: #f0f2f5; }
</style>
