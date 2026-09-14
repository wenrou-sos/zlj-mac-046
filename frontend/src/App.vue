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
        <span class="today">{{ today }}</span>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/cases')) return '/cases'
  return route.path
})
const today = new Date().toLocaleDateString('zh-CN', {
  year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
})
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
.today { color: #888; font-size: 13px; }
.main { background: #f0f2f5; }
</style>
