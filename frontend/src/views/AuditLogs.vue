<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent="load(1)">
        <el-form-item label="动作">
          <el-select v-model="filters.action" clearable placeholder="全部" style="width: 150px" @change="load(1)">
            <el-option v-for="(label, key) in actionMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作人">
          <el-input v-model="filters.actor" placeholder="账号ID" clearable style="width: 110px" @change="load(1)" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                          range-separator="至" start-placeholder="开始" end-placeholder="结束"
                          @change="load(1)" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="logs" v-loading="loading" stripe>
        <el-table-column prop="created_at" label="时间" width="150" />
        <el-table-column prop="actor_name" label="操作人" width="120">
          <template #default="{ row }">{{ row.actor_name || '匿名' }}</template>
        </el-table-column>
        <el-table-column label="动作" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="actionTag(row.action)">{{ row.action_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_name" label="对象" width="120">
          <template #default="{ row }">{{ row.target_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="case_number" label="相关案号" min-width="180">
          <template #default="{ row }">{{ row.case_number || '-' }}</template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="300" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" width="130">
          <template #default="{ row }">{{ row.ip || '-' }}</template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 14px; display: flex; justify-content: flex-end">
        <el-pagination
          background layout="prev, pager, next, total"
          :total="total" :page-size="pageSize" :current-page="page"
          @current-change="(p) => load(p)"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'

const actionMap = {
  login: '登录', logout: '退出登录', login_failed: '登录失败',
  grant: '授权', revoke: '撤权', expire: '借阅到期',
  case_view: '查看案件详情', conflict_check: '利益冲突检索', case_delete: '删除案件',
}
const actionTag = (a) => ({
  login: 'success', login_failed: 'danger', logout: 'info',
  grant: 'warning', revoke: 'danger', expire: 'info',
  case_view: 'primary', conflict_check: 'warning', case_delete: 'danger',
}[a])

const logs = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const dateRange = ref(null)
const filters = reactive({ action: '', actor: '' })

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const params = { page: p, page_size: pageSize }
    if (filters.action) params.action = filters.action
    if (filters.actor) params.actor = filters.actor
    if (dateRange.value) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const res = await api.get('/audit-logs/', { params })
    logs.value = res.data.results
    total.value = res.data.count
  } finally {
    loading.value = false
  }
}

onMounted(() => load(1))
</script>
