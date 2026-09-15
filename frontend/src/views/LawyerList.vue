<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="搜索">
          <el-input
            v-model="search"
            placeholder="姓名/执业证号"
            clearable
            style="width: 220px"
            @change="load"
          />
        </el-form-item>
        <el-form-item>
          <el-button v-if="auth.user.is_admin" type="primary" @click="openDialog()">新建律师</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="lawyers" v-loading="loading" stripe>
        <el-table-column prop="name" label="姓名" width="120" />
        <el-table-column prop="bar_number" label="执业证号" min-width="180" />
        <el-table-column prop="title_display" label="职称" width="110" />
        <el-table-column prop="phone" label="电话" width="140" />
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column prop="case_count" label="在办案件" width="90" align="center" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <template v-if="auth.user.is_admin">
              <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除该律师？" @confirm="remove(row)">
                <template #reference>
                  <el-button link type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
            <span v-else class="sub">仅管理员可维护</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑律师' : '新建律师'" width="440px">
      <el-form label-width="90px">
        <el-form-item label="姓名" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="执业证号" required>
          <el-input v-model="form.bar_number" />
        </el-form-item>
        <el-form-item label="职称">
          <el-select v-model="form.title" style="width: 100%">
            <el-option label="合伙人" value="partner" />
            <el-option label="资深律师" value="senior" />
            <el-option label="律师" value="lawyer" />
            <el-option label="律师助理" value="assistant" />
          </el-select>
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { auth } from '../auth'

const lawyers = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const search = ref('')
const blank = { id: null, name: '', bar_number: '', title: 'lawyer', phone: '', email: '' }
const form = reactive({ ...blank })

async function load() {
  loading.value = true
  try {
    const res = await api.get('/lawyers/', { params: search.value ? { search: search.value } : {} })
    lawyers.value = res.data
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  Object.assign(form, blank, row || {})
  dialogVisible.value = true
}

async function save() {
  if (!form.name || !form.bar_number) {
    ElMessage.warning('姓名和执业证号必填')
    return
  }
  saving.value = true
  try {
    if (form.id) await api.put(`/lawyers/${form.id}/`, form)
    else await api.post('/lawyers/', form)
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await api.delete(`/lawyers/${row.id}/`)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.sub { color: #999; font-size: 12px; }
</style>
