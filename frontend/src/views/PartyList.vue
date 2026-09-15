<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="搜索">
          <el-input
            v-model="filters.search"
            placeholder="姓名/名称/证件号"
            clearable
            style="width: 220px"
            @change="load"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filters.party_type" clearable placeholder="全部" style="width: 130px" @change="load">
            <el-option label="自然人" value="person" />
            <el-option label="法人/组织" value="org" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="openDialog()">新建当事人</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="parties" v-loading="loading" stripe>
        <el-table-column prop="name" label="姓名/名称" min-width="200" />
        <el-table-column prop="party_type_display" label="类型" width="110" />
        <el-table-column prop="id_number" label="证件号/信用代码" min-width="190">
          <template #default="{ row }">{{ row.id_number || '-' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="140">
          <template #default="{ row }">{{ row.phone || '-' }}</template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.address || '-' }}</template>
        </el-table-column>
        <el-table-column prop="case_count" label="涉及案件" width="90" align="center" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除该当事人？案件中的关联记录也会删除" @confirm="remove(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑当事人' : '新建当事人'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="姓名/名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.party_type">
            <el-radio value="person">自然人</el-radio>
            <el-radio value="org">法人/组织</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="证件号">
          <el-input v-model="form.id_number" placeholder="身份证号/统一社会信用代码" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
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

const parties = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const filters = reactive({ search: '', party_type: '' })
const blank = { id: null, name: '', party_type: 'person', id_number: '', phone: '', address: '', notes: '' }
const form = reactive({ ...blank })

async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    const res = await api.get('/parties/', { params })
    parties.value = res.data
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  Object.assign(form, blank, row || {})
  dialogVisible.value = true
}

async function save() {
  if (!form.name) {
    ElMessage.warning('姓名/名称必填')
    return
  }
  saving.value = true
  try {
    if (form.id) await api.put(`/parties/${form.id}/`, form)
    else await api.post('/parties/', form)
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await api.delete(`/parties/${row.id}/`)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>
