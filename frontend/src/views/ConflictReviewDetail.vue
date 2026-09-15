<template>
  <div v-loading="loading">
    <template v-if="r.id">
      <!-- 抬头 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <div class="head">
          <div>
            <div class="title-row">
              <span class="title">{{ r.review_number }}</span>
              <el-tag :type="statusType(r.status)" effect="dark">{{ r.status_display }}</el-tag>
              <el-tag :type="riskType(r.risk_level)" effect="plain">
                {{ riskText(r.risk_level) }}
              </el-tag>
              <el-tag v-if="r.has_prohibited" type="danger" effect="dark">含禁止性冲突</el-tag>
              <el-tag v-else-if="r.needs_exception" type="warning" effect="dark">须例外授权</el-tag>
            </div>
            <div class="sub">
              <router-link :to="`/cases/${r.case}`" class="link">{{ r.case_title }}</router-link>
              （{{ r.case_number }}） · 拟承接当事人：<b>{{ r.party_name }}</b>
              · {{ r.proposed_role_display }}
              <el-tag v-if="r.proposed_is_client" type="success" size="small">作为本所客户</el-tag>
              <el-tag v-else size="small" type="info">作为对方当事人</el-tag>
            </div>
          </div>
          <el-button @click="$router.push('/conflict-reviews')">返回列表</el-button>
        </div>

        <el-descriptions :column="3" border size="small" style="margin-top: 12px">
          <el-descriptions-item label="申请人">{{ r.applicant_name }}</el-descriptions-item>
          <el-descriptions-item label="指定复核人">{{ r.reviewer_name }}</el-descriptions-item>
          <el-descriptions-item label="申请时间">{{ r.created_at }}</el-descriptions-item>
          <el-descriptions-item label="例外授权依据" :span="2">
            {{ r.exception_basis || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="例外适用期限">
            {{ r.exception_expire_date || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="复核意见" :span="3">
            {{ r.decision_remark || '—' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="r.used_at" label="承接使用" :span="3">
            已于 {{ r.used_at }} 由 {{ r.used_by_name || '' }} 用于承接，结论归档
          </el-descriptions-item>
          <el-descriptions-item v-if="r.superseded_by" label="接续复核单" :span="3">
            <router-link class="link" :to="`/conflict-reviews/${r.superseded_by}`">
              已由新复核单接续 → #{{ r.superseded_by }}
            </router-link>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 操作区 -->
        <div class="actions">
          <template v-if="r.status === 'pending' && isReviewer">
            <el-button type="success" @click="openDecide('approve')">批准</el-button>
            <el-button type="danger" @click="openDecide('reject')">拒绝</el-button>
            <el-button type="warning" @click="openDecide('return')">退回补充材料</el-button>
          </template>
          <el-alert
            v-else-if="r.status === 'pending' && !isReviewer"
            type="info" :closable="false" class="inline-alert"
            :title="`等待复核人 ${r.reviewer_name} 审批；申请人不能审批自己的申请`"
          />
          <el-button
            v-if="r.status === 'returned' && isApplicant"
            type="primary" @click="suppVisible = true"
          >补充材料并重新提交</el-button>
          <el-button
            v-if="canRecheck && isApplicant"
            type="warning" @click="recheckVisible = true"
          >发起重新复核</el-button>
          <el-button
            v-if="canAccept" type="success"
            @click="$router.push(`/cases/${r.case}`)"
          >前往案件承接当事人</el-button>
        </div>
      </el-card>

      <el-card v-if="r.status === 'approved' && r.is_active" shadow="never" style="margin-bottom:16px">
        <el-alert type="success" :closable="false"
          title="批准结论当前有效，可凭此单承接；承接时将再次核对未使用、例外未到期、涉案关系未变更。" />
      </el-card>

      <el-tabs v-model="tab">
        <!-- 风险依据快照 -->
        <el-tab-pane label="风险依据快照" name="snapshot">
          <el-alert
            v-for="(f, i) in snapshot.findings"
            :key="i"
            :type="f.prohibited ? 'error' : f.level === 'medium' ? 'warning' : 'success'"
            :closable="false" :title="f.message" style="margin-bottom: 8px"
          />
          <el-alert
            v-if="!snapshot.findings.length" type="success" :closable="false"
            title="申请时点未发现任何冲突情形" style="margin-bottom: 8px"
          />
          <el-descriptions :column="4" border size="small" style="margin-top:12px">
            <el-descriptions-item label="当事人">{{ snapParty.name }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ snapParty.party_type_display }}</el-descriptions-item>
            <el-descriptions-item label="证件号" :span="2">{{ snapParty.id_number || '—' }}</el-descriptions-item>
            <el-descriptions-item label="联系电话">{{ snapParty.phone || '—' }}</el-descriptions-item>
            <el-descriptions-item label="住所" :span="3">{{ snapParty.address || '—' }}</el-descriptions-item>
            <el-descriptions-item label="快照生成时间" :span="4">{{ snapshot.evaluated_at }}</el-descriptions-item>
          </el-descriptions>

          <div class="table-caption">申请时点该当事人在本所的全部涉案关系（快照）</div>
          <el-table :data="snapshot.involvements" size="small" style="margin-top:6px">
            <el-table-column label="案件" min-width="220">
              <template #default="{ row }">
                {{ row.case_title }}<div class="sub">{{ row.case_number }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="stage_display" label="阶段" width="90" />
            <el-table-column prop="role_display" label="诉讼地位" width="110" />
            <el-table-column label="本所客户" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_client" type="success" size="small">是</el-tag>
                <span v-else>否</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 依据材料 -->
        <el-tab-pane :label="`依据材料 (${r.materials.length})`" name="materials">
          <el-table :data="r.materials" size="small">
            <el-table-column prop="name" label="材料名称" min-width="200" />
            <el-table-column prop="source" label="来源/出具方" min-width="150" />
            <el-table-column label="提交人" width="120">
              <template #default="{ row }">{{ row.uploaded_by_name }}</template>
            </el-table-column>
            <el-table-column prop="uploaded_at" label="提交时间" width="150" />
          </el-table>
          <el-empty v-if="!r.materials.length" description="暂无材料" :image-size="60" />
        </el-tab-pane>

        <!-- 全程流水 -->
        <el-tab-pane label="全过程流水" name="logs">
          <el-timeline style="padding-top: 10px">
            <el-timeline-item
              v-for="log in r.logs" :key="log.id"
              :timestamp="log.created_at"
              :type="logIcon(log.action)"
            >
              <el-tag size="small" :type="logIcon(log.action)">{{ log.action_display }}</el-tag>
              <span class="log-actor">{{ log.actor_name || '系统' }}</span>
              <div class="sub">{{ log.detail }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 审批对话框 -->
    <el-dialog v-model="decideVisible" :title="decideTitle" width="560px">
      <el-alert
        v-if="decideForm.decision === 'approve' && r.has_prohibited"
        type="error" :closable="false"
        title="该单含本所明确禁止的利益冲突，按规定不得批准，也不适用例外授权；请改用拒绝。"
        style="margin-bottom: 12px"
      />
      <el-form label-width="104px">
        <template v-if="decideForm.decision === 'approve'">
          <el-alert
            v-if="r.needs_exception" type="warning" :closable="false"
            title="属可有条件豁免的冲突：必须登记例外授权依据与适用期限，否则不能批准。"
            style="margin-bottom: 12px"
          />
          <el-form-item label="例外授权依据" :required="r.needs_exception">
            <el-input v-model="decideForm.exception_basis" type="textarea" :rows="2"
              placeholder="如 利益冲突审查委员会2026第X号决议、当事人知情同意书编号" />
          </el-form-item>
          <el-form-item label="例外适用期限" :required="r.needs_exception">
            <el-date-picker v-model="decideForm.exception_expire_date" type="date"
              value-format="YYYY-MM-DD" placeholder="授权有效截止日" />
          </el-form-item>
        </template>
        <el-form-item label="复核意见">
          <el-input v-model="decideForm.decision_remark" type="textarea" :rows="3"
            :placeholder="decideForm.decision === 'return' ? '请说明需要补充的材料' : '复核意见' " />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decideVisible = false">取消</el-button>
        <el-button :type="decideForm.decision === 'approve' ? 'success' : decideForm.decision === 'reject' ? 'danger' : 'warning'"
          :loading="saving" @click="submitDecide">确认</el-button>
      </template>
    </el-dialog>

    <!-- 补充材料 -->
    <el-dialog v-model="suppVisible" title="补充材料并重新提交" width="520px">
      <div v-for="(m, i) in suppMaterials" :key="i" class="mat-row">
        <el-input v-model="m.name" placeholder="材料名称" style="width:200px" />
        <el-input v-model="m.source" placeholder="来源/出具方" style="width:180px" />
        <el-button link type="danger" @click="suppMaterials.splice(i, 1)">删除</el-button>
      </div>
      <el-button link type="primary" @click="suppMaterials.push({ name: '', source: '' })">+ 添加材料</el-button>
      <template #footer>
        <el-button @click="suppVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitSupplement">提交补充</el-button>
      </template>
    </el-dialog>

    <!-- 重新复核 -->
    <el-dialog v-model="recheckVisible" title="发起重新复核" width="520px">
      <el-alert type="warning" :closable="false"
        title="系统已检测到相关涉案关系变更；将按当前数据重新评估风险并生成新复核单，旧单作废但全过程继续可查。"
        style="margin-bottom: 12px" />
      <el-form label-width="104px">
        <el-form-item label="复核人">
          <el-select v-model="recheckReviewer" filterable style="width:100%">
            <el-option v-for="l in identity.lawyers" :key="l.id"
              :label="`${l.name}（${l.title_display}）`" :value="l.id"
              :disabled="l.id === identity.lawyerId" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="recheckRemark" type="textarea" :rows="3"
            placeholder="说明关系变更情况（留空则自动生成）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="recheckVisible = false">取消</el-button>
        <el-button type="warning" :loading="saving" @click="submitRecheck">发起重新复核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { identity } from '../identity'

const route = useRoute()
const router = useRouter()
const id = route.params.id

const loading = ref(false)
const saving = ref(false)
const r = ref({ materials: [], logs: [], snapshot: {} })
const tab = ref('snapshot')

const decideVisible = ref(false)
const suppVisible = ref(false)
const recheckVisible = ref(false)
const decideForm = ref({})
const suppMaterials = ref([])
const recheckReviewer = ref(null)
const recheckRemark = ref('')

const statusMap = {
  pending: '待复核', approved: '已批准', rejected: '已拒绝',
  returned: '退回补充材料', superseded: '已重新复核', invalid: '已失效(关系变更)',
}
const riskType = (x) => ({ high: 'danger', medium: 'warning', low: 'success' }[x] || '')
const riskText = (x) => ({ high: '高风险', medium: '需关注', low: '低风险' }[x] || x)
const statusType = (s) => ({
  pending: 'warning', approved: 'success', rejected: 'danger',
  returned: 'info', superseded: 'info', invalid: 'danger',
}[s] || '')
function logIcon(a) {
  return {
    approve: 'success', reject: 'danger', return: 'warning',
    supplement: 'primary', supersede: 'warning', invalidate: 'danger',
    use: 'success', apply: 'primary',
  }[a] || ''
}

const snapshot = computed(() => r.value.snapshot || {})
const snapParty = computed(() => snapshot.value.party || {})
const isReviewer = computed(() => r.value.reviewer === identity.lawyerId)
const isApplicant = computed(() => r.value.applicant === identity.lawyerId)
const canRecheck = computed(() =>
  ['approved', 'superseded', 'invalid'].includes(r.value.status)
  && r.value.status !== 'pending')
const canAccept = computed(() => r.value.status === 'approved' && r.value.is_active)

const decideTitle = computed(() =>
  ({ approve: '批准承接', reject: '拒绝承接', return: '退回补充材料' }[decideForm.value.decision]))

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/conflict-reviews/${id}/`)
    r.value = res.data
  } finally {
    loading.value = false
  }
}

function openDecide(decision) {
  decideForm.value = {
    decision, decision_remark: '',
    exception_basis: r.value.exception_basis || '',
    exception_expire_date: r.value.exception_expire_date || null,
  }
  decideVisible.value = true
}

async function submitDecide() {
  saving.value = true
  try {
    await api.post(`/conflict-reviews/${id}/decide/`, decideForm.value)
    ElMessage.success('决定已提交并留痕')
    decideVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function submitSupplement() {
  const mats = suppMaterials.value.filter((m) => m.name)
  if (!mats.length) {
    ElMessage.warning('请至少填写一份材料')
    return
  }
  saving.value = true
  try {
    await api.post(`/conflict-reviews/${id}/supplement/`, { materials: mats })
    ElMessage.success('材料已补充，复核单重新进入待复核')
    suppVisible.value = false
    tab.value = 'materials'
    load()
  } finally {
    saving.value = false
  }
}

async function submitRecheck() {
  if (!recheckReviewer.value) {
    ElMessage.warning('请指定复核人')
    return
  }
  saving.value = true
  try {
    const res = await api.post(`/conflict-reviews/${id}/recheck/`, {
      reviewer: recheckReviewer.value,
      apply_remark: recheckRemark.value,
    })
    ElMessage.success('已生成新复核单')
    recheckVisible.value = false
    router.replace(`/conflict-reviews/${res.data.id}`)
    load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (!identity.lawyers.length) await import('../identity').then((m) => m.loadLawyers())
  load()
})
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; }
.title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.title { font-size: 18px; font-weight: 600; }
.sub { color: #999; font-size: 13px; margin-top: 4px; }
.link { color: #409eff; text-decoration: none; }
.actions { margin-top: 14px; display: flex; gap: 10px; align-items: center; }
.inline-alert { max-width: 600px; }
.mat-row { display: flex; gap: 8px; margin-bottom: 8px; }
.log-actor { margin-left: 8px; color: #666; font-size: 13px; }
.table-caption { font-weight: 600; font-size: 13px; margin-top: 12px; }
</style>
