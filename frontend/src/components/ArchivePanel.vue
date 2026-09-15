<template>
  <div class="archive-panel">
    <!-- ============ 已封存 ============ -->
    <template v-if="info.is_sealed">
      <el-alert
        type="success" :closable="false" show-icon
        :title="`卷宗 v${sealedVersion?.version_no || info.sealed_version} 已封存（${(sealedVersion?.sealed_at || '').replace('T', ' ').slice(0, 16)}）`"
        description="封存期间案件及庭期、材料、期限等记录只读，日常编辑与删除不能改写归档版本；再审或补充材料请申请重开。"
        style="margin-bottom: 12px"
      />
      <div class="tab-bar">
        <el-select v-model="viewVersionId" size="small" style="width: 300px">
          <el-option
            v-for="v in caseData.archive_versions"
            :key="v.id"
            :label="versionOptionLabel(v)"
            :value="v.id"
          />
        </el-select>
        <el-button size="small" @click="printSnapshot">打印归档卷宗</el-button>
        <el-button size="small" type="warning" @click="reopenDialog = true">
          申请重开（再审/补充材料）
        </el-button>
      </div>
      <ArchiveSnapshot :snapshot="viewSnapshot" />
    </template>

    <!-- ============ 待复核 ============ -->
    <template v-else-if="info.current_status === 'submitted'">
      <el-alert
        type="warning" :closable="false" show-icon
        :title="`卷宗 v${info.current_version} 已提交，等待复核人确认封存`"
        :description="`提交人：${submittedVersion?.submitted_by || '-'}　提交时间：${(submittedVersion?.submitted_at || '').replace('T', ' ').slice(0, 16)}`"
        style="margin-bottom: 12px"
      />
      <ArchiveSnapshot :snapshot="submittedSnapshot" />
      <div class="review-bar">
        <el-button @click="onCancelSubmit">撤回归档整理</el-button>
        <el-button type="danger" @click="openRejectDialog">复核退回</el-button>
        <el-button type="success" @click="openConfirmDialog">复核通过并封存</el-button>
      </div>
    </template>

    <!-- ============ 整理中 / 退回 / 未归档 ============ -->
    <template v-else>
      <el-alert
        v-if="info.current_status === 'rejected'"
        type="error" :closable="false" show-icon
        :title="`v${info.current_version} 被复核退回：${currentVersion?.reject_reason || ''}`"
        description="请根据退回原因修改整理内容后重新提交（版本号保持不变）。"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-else-if="caseData.stage === 'closed'"
        type="info" :closable="false" show-icon
        title="该案件已标记结案但尚未归档，请整理卷宗并经复核封存。"
        style="margin-bottom: 12px"
      />
      <div v-loading="prepLoading">
        <!-- 步骤 1：结案信息 -->
        <el-card shadow="never" style="margin-bottom: 12px">
          <template #header><b>① 结案信息</b></template>
          <el-form :model="form" label-width="100px">
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="结案日期" required>
                  <el-date-picker v-model="form.closed_date" type="date"
                    value-format="YYYY-MM-DD" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="整理人" required>
                  <el-input v-model="form.prepared_by" placeholder="姓名" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="结案摘要">
              <el-input v-model="form.summary" type="textarea" :rows="2"
                placeholder="结案方式、履行情况等摘要" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 步骤 2：未结事项逐项处置 -->
        <el-card shadow="never" style="margin-bottom: 12px">
          <template #header>
            <b>② 未结事项逐项处置</b>
            <span class="hint">系统已按期限、材料、庭期自动扫描（{{ items.length }} 项），逐项说明处置后才能提交</span>
          </template>
          <el-table :data="items" size="small" border>
            <el-table-column label="类别" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="kindTag(row.kind)">{{ kindLabel(row.kind) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="事项" min-width="160">
              <template #default="{ row }">
                <el-input v-if="row.kind === 'custom'" v-model="row.title" size="small"
                  placeholder="事项名称" />
                <span v-else>{{ row.title }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
            <el-table-column label="处置方式" width="150">
              <template #default="{ row }">
                <el-select v-model="row.disposition" size="small" placeholder="请选择">
                  <el-option v-for="(label, key) in dispositionMap" :key="key"
                    :label="label" :value="key" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="处置说明" min-width="200">
              <template #default="{ row }">
                <el-input v-model="row.disposition_note" size="small"
                  placeholder="逐项说明处置/移交/跟进情况" />
              </template>
            </el-table-column>
            <el-table-column width="70" align="center">
              <template #default="{ $index, row }">
                <el-button v-if="row.kind === 'custom'" link type="danger" size="small"
                  @click="items.splice($index, 1)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>未扫描到未办结期限、未签收材料或未来庭期</template>
          </el-table>
          <div style="margin-top: 10px">
            <el-button size="small" @click="addCustom">+ 添加其他未结事项</el-button>
          </div>
        </el-card>

        <!-- 步骤 3：提交复核 -->
        <el-card shadow="never">
          <template #header>
            <b>③ 提交复核</b>
            <span class="hint">提交时将固定清单指纹；封存时复核，期间有变更会要求重新核对，不会封存过时清单</span>
          </template>
          <el-form label-width="100px">
            <el-form-item label="提交人">
              <el-input v-model="form.submitted_by" style="width: 220px" placeholder="姓名" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="submitting" @click="onSubmit">
                提交复核封存
              </el-button>
              <span class="hint">提交后由复核人逐项核对并确认，确认后生成固定归档版本</span>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </template>

    <!-- ===== 复核通过对话框 ===== -->
    <el-dialog v-model="confirmDialog" title="复核确认并封存" width="520px">
      <el-alert type="success" :closable="false" show-icon
        title="确认后将生成固定归档版本并冻结快照，案件进入只读封存状态。" style="margin-bottom: 12px" />
      <el-form label-width="90px">
        <el-form-item label="复核人" required>
          <el-input v-model="reviewForm.reviewer" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="复核意见">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="2"
            placeholder="材料齐全，同意封存归档" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmDialog = false">取消</el-button>
        <el-button type="success" :loading="acting" @click="onConfirm">确认封存</el-button>
      </template>
    </el-dialog>

    <!-- ===== 退回对话框 ===== -->
    <el-dialog v-model="rejectDialog" title="复核退回" width="520px">
      <el-form label-width="90px">
        <el-form-item label="复核人" required>
          <el-input v-model="reviewForm.reviewer" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="退回原因" required>
          <el-input v-model="reviewForm.reject_reason" type="textarea" :rows="3"
            placeholder="说明需要补充/修改的内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectDialog = false">取消</el-button>
        <el-button type="danger" :loading="acting" @click="onReject">确认退回</el-button>
      </template>
    </el-dialog>

    <!-- ===== 申请重开 ===== -->
    <el-dialog v-model="reopenDialog" title="申请重开卷宗" width="560px">
      <el-alert type="warning" :closable="false" show-icon
        title="再审或补充材料需说明原因，经批准后方可恢复编辑；批准记录与旧卷宗一并保留。"
        style="margin-bottom: 12px" />
      <el-form label-width="100px">
        <el-form-item label="重开原因" required>
          <el-radio-group v-model="reopenForm.reason_type">
            <el-radio value="retrial">再审</el-radio>
            <el-radio value="supplement">补充材料</el-radio>
            <el-radio value="other">其他</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="原因说明" required>
          <el-input v-model="reopenForm.reason" type="textarea" :rows="3"
            placeholder="如：高院裁定提审 / 当事人补充关键证据" />
        </el-form-item>
        <el-form-item label="申请人">
          <el-input v-model="reopenForm.applicant" placeholder="姓名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reopenDialog = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="onReopenApply">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- ===== 重开记录 / 审批 ===== -->
    <el-card v-if="caseData.reopen_requests?.length" shadow="never" style="margin-top: 16px">
      <template #header><b>重开申请与审批记录</b></template>
      <el-timeline>
        <el-timeline-item
          v-for="r in caseData.reopen_requests" :key="r.id"
          :timestamp="(r.decided_at || r.created_at)?.replace('T', ' ').slice(0, 16)"
          :type="r.status === 'approved' ? 'success' : r.status === 'rejected' ? 'danger' : 'warning'">
          <div>
            <el-tag size="small" :type="r.status === 'approved' ? 'success'
              : r.status === 'rejected' ? 'danger' : 'warning'">{{ r.status_display }}</el-tag>
            <b style="margin-left: 6px">{{ r.reason_type_display }}</b>
            <span class="hint">申请人 {{ r.applicant || '-' }}；基于卷宗 v{{ r.archive_version_no || '-' }}</span>
          </div>
          <div class="sub">{{ r.reason }}</div>
          <div v-if="r.status !== 'pending'" class="sub">
            审批人：{{ r.approver }}　意见：{{ r.approval_comment || '-' }}
            <span v-if="r.status === 'approved'">　重开后阶段：{{ r.next_stage_display }}</span>
          </div>
          <div v-else style="margin-top: 6px">
            <el-button size="small" type="success" @click="openApprove(r)">批准重开</el-button>
            <el-button size="small" type="danger" @click="openDeny(r)">不予批准</el-button>
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- ===== 批准重开 ===== -->
    <el-dialog v-model="approveDialog" title="批准重开" width="520px">
      <el-form label-width="100px">
        <el-form-item label="批准人" required>
          <el-input v-model="decideForm.approver" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="重开后阶段">
          <el-select v-model="decideForm.next_stage" style="width: 100%">
            <el-option v-for="(label, key) in stageMap" :key="key"
              :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="审批意见">
          <el-input v-model="decideForm.comment" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="approveDialog = false">取消</el-button>
        <el-button type="success" :loading="acting" @click="onDecide(true)">确认批准</el-button>
      </template>
    </el-dialog>

    <!-- ===== 不批准 ===== -->
    <el-dialog v-model="denyDialog" title="不予批准重开" width="520px">
      <el-form label-width="100px">
        <el-form-item label="审批人" required>
          <el-input v-model="decideForm.approver" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="意见" required>
          <el-input v-model="decideForm.comment" type="textarea" :rows="3"
            placeholder="说明不予批准的理由" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="denyDialog = false">取消</el-button>
        <el-button type="danger" :loading="acting" @click="onDecide(false)">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import ArchiveSnapshot from './ArchiveSnapshot.vue'

const props = defineProps({
  caseData: { type: Object, required: true },
})
const emit = defineEmits(['refresh'])

const stageMap = { filing: '立案', first: '一审', second: '二审', retrial: '再审', enforcement: '执行', closed: '结案' }
const kindLabelMap = { deadline: '未办结期限', material: '未结材料', hearing: '未来庭期', custom: '其他事项' }
const dispositionMap = {
  completed: '已完成', handover: '已移交处理', followup: '继续跟进',
  waived: '当事人放弃/终结', other: '其他处置',
}
const kindTag = (k) => ({ deadline: 'danger', material: 'warning', hearing: 'primary', custom: 'info' }[k] || '')
const kindLabel = (k) => kindLabelMap[k] || k

const info = computed(() => props.caseData.archive || {})
const versions = computed(() => props.caseData.archive_versions || [])
const currentVersion = computed(() =>
  versions.value.find((v) => v.version_no === info.value.current_version) || null)
const sealedVersion = computed(() =>
  versions.value.find((v) => v.version_no === info.value.sealed_version
                       && v.status === 'sealed') || null)
const submittedVersion = computed(() =>
  info.value.current_status === 'submitted' ? currentVersion.value : null)

const prepLoading = ref(false)
const submitting = ref(false)
const acting = ref(false)
const form = reactive({ closed_date: '', summary: '', prepared_by: '', submitted_by: '' })
const items = ref([])
let lastFingerprint = ''

const submittedSnapshot = ref(null)
const snapshotLoading = ref(false)

/* ---------- 版本快照查看 ---------- */
const viewVersionId = ref(null)
const snapshotCache = reactive({})
const viewSnapshot = computed(() =>
  viewVersionId.value ? snapshotCache[viewVersionId.value] : null)

async function loadVersionSnapshot(id) {
  if (!id || snapshotCache[id]) return
  snapshotLoading.value = true
  try {
    const res = await api.get(`/archive-versions/${id}/`)
    snapshotCache[id] = res.data.snapshot
  } finally {
    snapshotLoading.value = false
  }
}
watch(viewVersionId, (id) => loadVersionSnapshot(id))

function versionOptionLabel(v) {
  const state = { sealed: '已封存', reopened: '已重开(历史)', rejected: '复核退回',
                  submitted: '待复核', draft: '整理中' }[v.status] || v.status
  const at = v.sealed_at ? `（${v.sealed_at.slice(0, 10)}封存）` : ''
  return `v${v.version_no} ${state}${at}`
}

/* ---------- 整理页数据 ---------- */
async function loadPrepare() {
  prepLoading.value = true
  try {
    const res = await api.get(`/cases/${props.caseData.id}/archive/prepare/`)
    lastFingerprint = res.data.fingerprint
    items.value = (res.data.suggested_pending_items || []).map((r) => ({
      kind: r.kind, ref_id: r.ref_id, item_key: r.item_key,
      title: r.title, detail: r.detail,
      disposition: r.disposition || '', disposition_note: r.disposition_note || '',
    }))
  } finally {
    prepLoading.value = false
  }
}

function addCustom() {
  items.value.push({
    kind: 'custom', item_key: '', ref_id: null,
    title: '', detail: '', disposition: '', disposition_note: '',
  })
}

async function onSubmit() {
  if (!form.closed_date) return ElMessage.warning('请选择结案日期')
  if (!form.prepared_by) return ElMessage.warning('请填写整理人')
  if (!form.submitted_by) form.submitted_by = form.prepared_by
  for (const it of items.value) {
    if (it.kind === 'custom' && !it.item_key) {
      if (!it.title) return ElMessage.warning('请填写自定义事项名称')
      it.item_key = `custom-${it.title}`
    }
  }
  const bad = items.value.find((i) => !i.disposition || !i.disposition_note)
  if (bad) return ElMessage.warning(`请为未结事项「${bad.title}」选择处置方式并填写说明`)
  submitting.value = true
  try {
    await api.post(`/cases/${props.caseData.id}/archive/submit/`, {
      ...form, fingerprint: lastFingerprint, pending_items: items.value,
    })
    ElMessage.success('已提交复核')
    emit('refresh')
  } finally {
    submitting.value = false
  }
}

/* ---------- 复核 ---------- */
const confirmDialog = ref(false)
const rejectDialog = ref(false)
const reviewForm = reactive({ reviewer: '', comment: '', reject_reason: '' })

function openConfirmDialog() {
  Object.assign(reviewForm, { reviewer: '', comment: '', reject_reason: '' })
  confirmDialog.value = true
}
function openRejectDialog() {
  Object.assign(reviewForm, { reviewer: '', comment: '', reject_reason: '' })
  rejectDialog.value = true
}

async function onConfirm() {
  if (!reviewForm.reviewer) return ElMessage.warning('请填写复核人')
  acting.value = true
  try {
    await api.post(`/cases/${props.caseData.id}/archive/confirm/`, {
      version_no: info.value.current_version,
      reviewer: reviewForm.reviewer, review_comment: reviewForm.comment,
    })
    ElMessage.success('卷宗已封存归档')
    confirmDialog.value = false
    emit('refresh')
  } catch (e) {
    await handleConflict(e)
  } finally {
    acting.value = false
  }
}

async function onReject() {
  if (!reviewForm.reviewer) return ElMessage.warning('请填写复核人')
  if (!reviewForm.reject_reason) return ElMessage.warning('请填写退回原因')
  acting.value = true
  try {
    await api.post(`/cases/${props.caseData.id}/archive/reject/`, {
      version_no: info.value.current_version,
      reviewer: reviewForm.reviewer, reject_reason: reviewForm.reject_reason,
    })
    ElMessage.success('已退回整理人')
    rejectDialog.value = false
    emit('refresh')
  } finally {
    acting.value = false
  }
}

async function onCancelSubmit() {
  try {
    await ElMessageBox.confirm('撤回归档后可继续编辑整理内容，确定撤回？', '撤回归档', {
      type: 'warning', confirmButtonText: '撤回', cancelButtonText: '取消',
    })
  } catch { return }
  await api.post(`/cases/${props.caseData.id}/archive/cancel/`,
    { version_no: info.value.current_version })
  ElMessage.success('已撤回')
  emit('refresh')
}

/* ---------- 并发冲突 ---------- */
async function handleConflict(e) {
  const data = e.response?.data
  if (e.response?.status !== 409 || !data) return
  const sections = (data.changed_sections || []).map((s) => s.label).join('、')
  const stale = (data.stale_items || [])
    .map((i) => `• ${i.title}（${i.reason}）`).join('\n')
  await ElMessageBox.alert(
    `${data.detail || '清单已过期'}\n\n` +
    (sections ? `发生变化的信息：${sections}\n` : '') +
    (stale ? `未结事项差异：\n${stale}\n` : '') +
    '\n请撤回归档，按最新案件信息重新核对后再提交封存。',
    '归档确认：案件已发生并发变更', { type: 'error', confirmButtonText: '知道了' })
}

/* ---------- 重开 ---------- */
const reopenDialog = ref(false)
const reopenForm = reactive({ reason_type: 'retrial', reason: '', applicant: '' })

async function onReopenApply() {
  if (!reopenForm.reason.trim()) return ElMessage.warning('请填写重开原因')
  acting.value = true
  try {
    await api.post(`/cases/${props.caseData.id}/reopen/`, { ...reopenForm })
    ElMessage.success('重开申请已提交，等待批准')
    reopenDialog.value = false
    Object.assign(reopenForm, { reason_type: 'retrial', reason: '', applicant: '' })
    emit('refresh')
  } finally {
    acting.value = false
  }
}

const approveDialog = ref(false)
const denyDialog = ref(false)
const decideForm = reactive({ id: null, approver: '', comment: '', next_stage: 'retrial' })

function openApprove(r) {
  Object.assign(decideForm, { id: r.id, approver: '', comment: '', next_stage: 'retrial' })
  approveDialog.value = true
}
function openDeny(r) {
  Object.assign(decideForm, { id: r.id, approver: '', comment: '', next_stage: 'retrial' })
  denyDialog.value = true
}
async function onDecide(approve) {
  if (!decideForm.approver) return ElMessage.warning('请填写审批人')
  if (!approve && !decideForm.comment.trim()) return ElMessage.warning('请填写不予批准的意见')
  acting.value = true
  try {
    const url = `/reopen-requests/${decideForm.id}/${approve ? 'approve' : 'reject'}/`
    await api.post(url, {
      approver: decideForm.approver, approval_comment: decideForm.comment,
      next_stage: decideForm.next_stage,
    })
    ElMessage.success(approve ? '已批准重开，案件恢复可编辑' : '已不予批准')
    approveDialog.value = false
    denyDialog.value = false
    emit('refresh')
  } finally {
    acting.value = false
  }
}

/* ---------- 打印 ---------- */
function printSnapshot() {
  const snap = viewSnapshot.value
  if (!snap) return
  const rows = (list, cols) => list.length
    ? `<table><tr>${cols.map((c) => `<th>${c[1]}</th>`).join('')}</tr>` +
      list.map((r) => `<tr>${cols.map((c) => `<td>${r[c[0]] ?? ''}</td>`).join('')}</tr>`).join('') +
      '</table>'
    : '<p>无</p>'
  const win = window.open('', '_blank')
  win.document.write(`<html><head><meta charset="utf-8"><title>${snap.case.case_number} 归档卷宗</title>
    <style>body{font-family:sans-serif;padding:32px;color:#222}h2{margin:0}h3{border-left:4px solid #409eff;padding-left:8px;margin-top:24px}
    table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #999;padding:6px 8px;text-align:left}
    .meta{color:#666;font-size:13px;margin:8px 0 16px}</style></head><body>
    <h2>${snap.case.title}</h2>
    <div class="meta">案号：${snap.case.case_number}　结案日期：${snap.case.closed_date}　封存时间：${snap.generated_at}
    <br>整理人：${snap.prepared_by}　复核人：${snap.reviewer}　摘要：${snap.case.summary || ''}</div>
    <h3>当事人</h3>${rows(snap.parties, [['name', '姓名/名称'], ['role', '地位'], ['id_number', '证件号'], ['phone', '电话']])}
    <h3>承办律师</h3>${rows(snap.lawyers, [['name', '姓名'], ['role', '角色'], ['title', '职称'], ['bar_number', '执业证号']])}
    <h3>诉讼阶段</h3>${rows(snap.stages, [['log_date', '日期'], ['stage', '阶段'], ['notes', '备注']])}
    <h3>庭期</h3>${rows(snap.hearings, [['hearing_time', '时间'], ['location', '地点'], ['judge', '法官']])}
    <h3>材料</h3>${rows(snap.materials, [['name', '名称'], ['status', '状态'], ['submitted_to', '对象'], ['submit_date', '日期']])}
    <h3>期限</h3>${rows(snap.deadlines, [['due_date', '截止'], ['title', '事项'], ['deadline_type', '类型'], ['is_done', '办结']])}
    <h3>未结事项处置</h3>${rows(snap.pending_items, [['kind', '类别'], ['title', '事项'], ['disposition', '处置'], ['disposition_note', '说明']])}
    </body></html>`)
  win.document.close()
  win.print()
}

/* ---------- 初始化 ---------- */
function bootstrap() {
  submittedSnapshot.value = null
  const st = info.value.current_status
  if (st === 'submitted') {
    const v = versions.value.find((x) => x.version_no === info.value.current_version)
    if (v) loadVersionSnapshot(v.id).then(() => {
      submittedSnapshot.value = snapshotCache[v.id]
    })
  } else if (info.value.is_sealed) {
    if (sealedVersion.value) viewVersionId.value = sealedVersion.value.id
  } else {
    Object.assign(form, {
      closed_date: currentVersion.value?.closed_date || new Date().toISOString().slice(0, 10),
      summary: currentVersion.value?.summary || '',
      prepared_by: currentVersion.value?.prepared_by || '',
      submitted_by: currentVersion.value?.submitted_by || '',
    })
    loadPrepare()
  }
}

bootstrap()
watch(() => props.caseData.id, () => bootstrap())
watch(() => [info.value.current_status, info.value.is_sealed], () => bootstrap())
</script>

<style scoped>
.hint { color: #999; font-size: 12px; font-weight: normal; margin-left: 8px; }
.tab-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.review-bar { margin-top: 14px; text-align: right; }
.sub { color: #888; font-size: 13px; margin-top: 2px; }
</style>
