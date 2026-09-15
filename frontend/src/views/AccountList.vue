<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="搜索">
          <el-input v-model="keyword" placeholder="登录名/姓名" clearable
                    style="width: 200px" @change="load" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="openDialog()">新建账号</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="display_name" label="姓名" width="120" />
        <el-table-column prop="username" label="登录名" width="120" />
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.profile.role)" size="small" effect="dark">
              {{ row.profile.role_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="绑定律师档案" min-width="140">
          <template #default="{ row }">{{ row.profile.lawyer_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small">启用</el-tag>
            <el-tag v-else type="danger" size="small">已停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login" label="最近登录" width="150">
          <template #default="{ row }">{{ row.last_login || '从未登录' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button link type="warning" @click="resetDialog(row)">重置密码</el-button>
            <el-popconfirm
              :title="row.is_active ? '停用后该账号立即失去所有访问权限并强制下线，确定？' : '确定启用该账号？'"
              @confirm="toggleActive(row)"
            >
              <template #reference>
                <el-button link :type="row.is_active ? 'danger' : 'success'">
                  {{ row.is_active ? '停用' : '启用' }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑账号' : '新建账号'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="登录名" required>
          <el-input v-model="form.username" :disabled="!!form.id" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item v-if="!form.id" label="初始密码" required>
          <el-input v-model="form.password" placeholder="至少 6 位" show-password />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.display_name_input" placeholder="账号显示名" />
        </el-form-item>
        <el-form-item label="账号角色" required>
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="(label, key) in roleMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定律师档案">
          <el-select v-model="form.lawyer" clearable filterable style="width: 100%"
                     placeholder="律师账号建议绑定，绑定后按承办案件自动授权">
            <el-option v-for="l in lawyers" :key="l.id"
                       :label="`${l.name}（${l.title_display}）`" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-alert v-if="form.lawyer" type="info" :closable="false"
                  title="绑定后，该账号将随律师的承办关系自动获得案件访问权限（主办/协办）；解除绑定或移除承办立即撤权。" />
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pwdVisible" :title="`重置密码 - ${pwdTarget?.display_name}`" width="420px">
      <el-input v-model="newPassword" type="password" show-password placeholder="新密码（至少6位）" />
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReset">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const roleMap = { admin: '管理员', lead: '主办律师', assist: '协办律师', reader: '只读助理' }
const roleTag = (r) => ({ admin: 'danger', lead: 'success', assist: 'warning', reader: 'info' }[r])

const users = ref([])
const lawyers = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const dialogVisible = ref(false)
const blank = {
  id: null, username: '', password: '', display_name_input: '',
  role: 'reader', lawyer: null,
}
const form = reactive({ ...blank })

const pwdVisible = ref(false)
const pwdTarget = ref(null)
const newPassword = ref('')

async function load() {
  loading.value = true
  try {
    const res = await api.get('/accounts/')
    users.value = keyword.value
      ? res.data.filter((u) => u.username.includes(keyword.value) || u.display_name.includes(keyword.value))
      : res.data
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  Object.assign(form, blank)
  if (row) {
    Object.assign(form, {
      id: row.id, username: row.username,
      display_name_input: row.display_name,
      role: row.profile.role, lawyer: row.profile.lawyer,
    })
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.username || (!form.id && !form.password)) {
    ElMessage.warning('登录名和初始密码必填')
    return
  }
  if (!form.id && form.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await api.put(`/accounts/${form.id}/`, {
        username: form.username,
        last_name: form.display_name_input,
        profile: { role: form.role, lawyer: form.lawyer },
      })
    } else {
      await api.post('/accounts/', {
        username: form.username, password: form.password,
        last_name: form.display_name_input,
        role: form.role, lawyer: form.lawyer,
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

function resetDialog(row) {
  pwdTarget.value = row
  newPassword.value = ''
  pwdVisible.value = true
}

async function submitReset() {
  if (newPassword.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  await api.post(`/accounts/${pwdTarget.value.id}/reset-password/`,
                 { password: newPassword.value })
  ElMessage.success('密码已重置')
  pwdVisible.value = false
}

async function toggleActive(row) {
  await api.patch(`/accounts/${row.id}/`, {
    is_active: !row.is_active, profile: {},
  })
  ElMessage.success(row.is_active ? '已停用' : '已启用')
  load()
}

onMounted(async () => {
  load()
  const res = await api.get('/lawyers/')
  lawyers.value = res.data
})
</script>
