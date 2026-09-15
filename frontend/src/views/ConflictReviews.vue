<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-alert
        type="info" :closable="false"
        title="冲突检查结果以复核单形式留痕：冻结当事人身份、涉案关系与风险依据快照，由指定复核人批准/拒绝/退回；本所禁止性冲突不得批准，例外须登记授权依据与期限。"
        style="margin-bottom: 14px"
      />
      <div class="toolbar">
        <el-radio-group v-model="scope" @change="load">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="todo">待我复核</el-radio-button>
          <el-radio-button label="mine_apply">我发起的</el-radio-button>
        </el-radio-group>
        <div class="filters">
          <el-select v-model="status" placeholder="状态" clearable style="width: 150px" @change="load">
            <el-option v-for="(label, key) in statusMap" :key="key" :label="label" :value="key" />
          </el-select>
          <el-select v-model="risk" placeholder="风险" clearable style="width: 130px" @change="load">
            <el-option label="高风险" value="high" />
            <el-option label="需关注" value="medium" />
            <el-option label="低风险" value="low" />
          </el-select>
          <el-button type="primary" :disabled="!identity.lawyerId" @click="applyVisible = true">
            发起复核申请
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="reviews" v-loading="loading" size="small">
        <el-table-column label="复核单号" width="140">
          <template #default="{ row }">
            <router-link :to="`/conflict-reviews/${row.id}`" class="link">{{ row.review_number }}</router-link>
          </template>
        </el-table-column>
        <el-table-column label="案件" min-width="200">
          <template #default="{ row }">
            {{ row.case_title }}
            <div class="sub">{{ row.case_number }}</div>
          </template>
        </el-table-column>
        <el-table-column label="当事人" min-width="150">
          <template #default="{ row }">{{ row.party_name }}</template>
        </el-table-column>
        <el-table-column label="拟承接" width="120">
          <template #default="{ row }">
            {{ row.proposed_role_display }}
            <el-tag v-if="row.proposed_is_client" type="success" size="small">客户</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="riskType(row.risk_level)" size="small" effect="dark">
              {{ riskText(row.risk_level) }}
            </el-tag>
            <el-tag v-if="row.has_prohibited" type="danger" size="small" effect="plain" style="margin-top:2px">禁止</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusMap[row.status] }}</el-tag>
            <div v-if="row.status === 'approved' && !row.is_active" class="sub">已使用/已过期</div>
            <div v-else-if="row.status === 'approved' && row.exception_expire_date" class="sub">
              例外至 {{ row.exception_expire_date }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="申请人 / 复核人" width="170">
          <template #default="{ row }">
            <div>{{ row.applicant_name }} → {{ row.reviewer_name }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="150" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/conflict-reviews/${row.id}`)">
              查看
            </el-button>
            <el-button
              v-if="canRecheck(row)" link type="warning" size="small"
              @click="$router.push(`/conflict-reviews/${row.id}`)"
            >重新复核</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <ApplyReviewDialog v-model="applyVisible" @created="onCreated" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { identity } from '../identity'
import ApplyReviewDialog from '../components/ApplyReviewDialog.vue'

const router = useRouter()
const reviews = ref([])
const loading = ref(false)
const scope = ref('')
const status = ref('')
const risk = ref('')
const applyVisible = ref(false)

const statusMap = {
  pending: '待复核', approved: '已批准', rejected: '已拒绝',
  returned: '退回补充材料', superseded: '已重新复核', invalid: '已失效(关系变更)',
}
const riskType = (r) => ({ high: 'danger', medium: 'warning', low: 'success' }[r])
const riskText = (r) => ({ high: '高风险', medium: '需关注', low: '低风险' }[r])
function statusType(s) {
  return {
    pending: 'warning', approved: 'success', rejected: 'danger',
    returned: 'info', superseded: 'info', invalid: 'danger',
  }[s] || ''
}
function canRecheck(row) {
  return ['approved', 'superseded', 'invalid'].includes(row.status)
    && row.applicant === identity.lawyerId
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (scope.value) params.scope = scope.value
    if (status.value) params.status = status.value
    if (risk.value) params.risk_level = risk.value
    const res = await api.get('/conflict-reviews/', { params })
    reviews.value = res.data
  } finally {
    loading.value = false
  }
}
function onCreated(created) {
  load()
  router.push(`/conflict-reviews/${created.id}`)
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 10px; }
.link { color: #409eff; text-decoration: none; }
.sub { color: #999; font-size: 12px; }
</style>
