<template>
  <div>
    <!-- 筛选栏 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="我的身份">
          <el-select v-model="filters.lawyer" clearable placeholder="全部交接" style="width: 180px" @change="load">
            <el-option v-for="l in lawyers" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 150px" @change="load">
            <el-option label="草稿" value="draft" />
            <el-option label="待核对" value="pending" />
            <el-option label="已退回补充" value="returned" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="canceled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="filters.activeOnly" @change="load">仅看进行中</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button @click="goCase">发起新交接</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="案件" min-width="240">
          <template #default="{ row }">
            <router-link :to="`/cases/${row.case}`" class="link">{{ row.case_title }}</router-link>
            <div class="sub">{{ row.case_number }}</div>
          </template>
        </el-table-column>
        <el-table-column label="交出人" width="100">
          <template #default="{ row }">{{ row.from_lawyer_name }}</template>
        </el-table-column>
        <el-table-column width="60" align="center">
          <template #default>→</template>
        </el-table-column>
        <el-table-column label="接收人" width="100">
          <template #default="{ row }">{{ row.to_lawyer_name }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status_display }}</el-tag>
            <el-tooltip v-if="row.stale" content="交接期间待办有变化，请补入最新清单后重新核对" placement="top">
              <el-tag type="danger" size="small" effect="dark" style="margin-left: 4px">清单已过期</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="待办" width="80" align="center">
          <template #default="{ row }">{{ row.pending_count }}</template>
        </el-table-column>
        <el-table-column label="发起时间" width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/handovers/${row.id}`)">处理</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无交接记录，可从案件详情页发起交接</template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const rows = ref([])
const lawyers = ref([])
const loading = ref(false)
const filters = reactive({ lawyer: null, status: '', activeOnly: false })

const statusType = (s) => ({
  draft: 'info', pending: 'warning', returned: 'danger',
  completed: 'success', canceled: 'info',
}[s])
const fmt = (t) => (t ? t.replace('T', ' ').slice(0, 16) : '-')

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.lawyer) params.lawyer = filters.lawyer
    if (filters.status) params.status = filters.status
    if (filters.activeOnly) params.active = 1
    const res = await api.get('/handovers/', { params })
    rows.value = res.data
  } finally {
    loading.value = false
  }
}

function goCase() {
  router.push('/cases')
}

onMounted(async () => {
  load()
  const res = await api.get('/lawyers/')
  lawyers.value = res.data
})
</script>

<style scoped>
.link { color: #409eff; text-decoration: none; }
.sub { color: #999; font-size: 12px; margin-top: 2px; }
</style>
