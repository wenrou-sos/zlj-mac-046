<template>
  <div>
    <!-- 筛选栏 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="搜索">
          <el-input
            v-model="filters.search"
            placeholder="案号 / 案件名称"
            clearable
            style="width: 220px"
            @change="load"
          />
        </el-form-item>
        <el-form-item label="诉讼阶段">
          <el-select v-model="filters.stage" clearable placeholder="全部" style="width: 130px" @change="load">
            <el-option v-for="(label, key) in stageMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="案件类型">
          <el-select v-model="filters.case_type" clearable placeholder="全部" style="width: 130px" @change="load">
            <el-option v-for="(label, key) in typeMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button v-if="canCreate" type="primary" @click="openDialog()">新建案件</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 案件表格 -->
    <el-card shadow="never">
      <el-table :data="cases" v-loading="loading" stripe>
        <el-table-column prop="case_number" label="案号" width="200" />
        <el-table-column label="案件名称" min-width="240">
          <template #default="{ row }">
            <router-link :to="`/cases/${row.id}`" class="link">{{ row.title }}</router-link>
          </template>
        </el-table-column>
        <el-table-column prop="case_type_display" label="类型" width="80" />
        <el-table-column label="阶段" width="90">
          <template #default="{ row }">
            <el-tag :type="stageTagType(row.stage)" size="small">{{ row.stage_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="承办律师" min-width="140">
          <template #default="{ row }">
            <span v-for="cl in row.case_lawyers" :key="cl.id" class="lawyer-tag">
              {{ cl.lawyer.name }}<span class="role">({{ cl.role_display }})</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="我的权限" width="110">
          <template #default="{ row }">
            <el-tag v-if="auth.user.is_admin" size="small" type="danger" effect="dark">管理员</el-tag>
            <el-tag v-else-if="row.my_access" size="small"
                    :type="row.my_access.role === 'reader' ? 'info' : 'success'">
              {{ row.my_access.role_display }}
              <span v-if="row.my_access.source === 'grant'" class="borrow">借阅</span>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="待办期限" width="90" align="center">
          <template #default="{ row }">
            <el-badge v-if="row.pending_deadline_count" :value="row.pending_deadline_count" type="warning" />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="filed_date" label="立案日期" width="110" />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/cases/${row.id}`)">详情</el-button>
            <el-button v-if="canEditCase(row)" link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button v-if="auth.user.is_admin" link type="warning"
                       @click="$router.push(`/cases/${row.id}?tab=access`)">授权</el-button>
            <el-popconfirm v-if="auth.user.is_admin" title="确定删除该案件及其全部关联记录？" @confirm="remove(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>暂无案件，点击右上角"新建案件"登记</template>
      </el-table>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑案件' : '新建案件'" width="640px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="案号" required>
          <el-input v-model="form.case_number" placeholder="如 (2026)京0105民初1234号" />
        </el-form-item>
        <el-form-item label="案件名称" required>
          <el-input v-model="form.title" placeholder="如 张三诉李四借款合同纠纷" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="案件类型">
              <el-select v-model="form.case_type" style="width: 100%">
                <el-option v-for="(label, key) in typeMap" :key="key" :label="label" :value="key" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="诉讼阶段">
              <el-select v-model="form.stage" style="width: 100%">
                <el-option v-for="(label, key) in stageMap" :key="key" :label="label" :value="key" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="案由">
              <el-input v-model="form.cause" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="受理法院">
              <el-input v-model="form.court" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="立案日期">
              <el-date-picker v-model="form.filed_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标的额(元)">
              <el-input-number v-model="form.amount" :min="0" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="案情简介">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { auth, canEditCase } from '../auth'

const stageMap = { filing: '立案', first: '一审', second: '二审', retrial: '再审', enforcement: '执行', closed: '结案' }
const typeMap = { civil: '民事', criminal: '刑事', administrative: '行政', arbitration: '仲裁', nonlit: '非诉讼' }

const canCreate = computed(() => auth.user.is_admin || auth.user.profile.role !== 'reader')

const cases = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const filters = reactive({ search: '', stage: '', case_type: '' })
const blank = { id: null, case_number: '', title: '', case_type: 'civil', stage: 'filing', cause: '', court: '', filed_date: null, amount: null, description: '' }
const form = reactive({ ...blank })

const stageTagType = (s) => ({ closed: 'info', enforcement: 'danger', second: 'warning', retrial: 'warning' }[s] || 'primary')

async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    const res = await api.get('/cases/', { params })
    cases.value = res.data
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  Object.assign(form, blank, row ? {
    id: row.id, case_number: row.case_number, title: row.title,
    case_type: row.case_type, stage: row.stage, cause: row.cause,
    court: row.court, filed_date: row.filed_date, amount: row.amount,
    description: row.description || '',
  } : {})
  dialogVisible.value = true
}

async function save() {
  if (!form.case_number || !form.title) {
    ElMessage.warning('案号和案件名称必填')
    return
  }
  saving.value = true
  try {
    if (form.id) await api.put(`/cases/${form.id}/`, form)
    else await api.post('/cases/', form)
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await api.delete(`/cases/${row.id}/`)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.link { color: #409eff; text-decoration: none; }
.lawyer-tag { margin-right: 8px; font-size: 13px; }
.role { color: #999; font-size: 12px; }
.borrow { margin-left: 2px; font-size: 11px; opacity: .85; }
</style>
