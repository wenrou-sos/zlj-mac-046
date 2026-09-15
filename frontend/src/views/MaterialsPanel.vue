<template>
  <div>
    <!-- 操作条 -->
    <div class="tab-bar">
      <el-input
        v-model="operator"
        size="small"
        placeholder="当前操作人（上传/定稿/提交留痕）"
        style="width: 260px"
        @change="saveOperator"
      >
        <template #prepend>操作人</template>
      </el-input>
      <el-button type="primary" size="small" style="margin-left: 12px" @click="openMaterialDialog">
        登记材料
      </el-button>
      <el-button type="success" size="small" @click="openSubmissionDialog">
        新建提交批次
      </el-button>
      <el-button size="small" @click="$emit('reload')">刷新</el-button>
      <el-tooltip content="操作人仅用于本模块的留痕记录，保存在本浏览器" placement="top">
        <el-icon style="margin-left: 6px; color: #999"><InfoFilled /></el-icon>
      </el-tooltip>
    </div>

    <!-- 提交批次 -->
    <el-divider content-position="left">
      提交批次（{{ submissions.length }}）
    </el-divider>
    <el-table :data="submissions" size="small" border>
      <el-table-column prop="submit_date" label="提交日期" width="105" />
      <el-table-column label="接收对象/方式" min-width="200">
        <template #default="{ row }">
          <div>{{ row.submitted_to }}<span v-if="row.receiver_name" class="sub-text">（{{ row.receiver_name }}）</span></div>
          <div class="sub-text">{{ methodText(row.method) }} · 经办人 {{ row.created_by }}</div>
        </template>
      </el-table-column>
      <el-table-column label="清单" min-width="220">
        <template #default="{ row }">
          <el-tag
            v-for="it in row.items"
            :key="it.id"
            size="small"
            style="margin: 2px"
            type="info"
          >{{ it.material_name }} v{{ it.version_no }} ×{{ it.copies }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态/回执" width="240">
        <template #default="{ row }">
          <el-tag :type="submissionTagType(row.status)" size="small" effect="dark">
            {{ row.status_display }}
          </el-tag>
          <el-tag v-if="row.resubmitted_from" type="warning" size="small" style="margin-left: 4px">
            补正重提
          </el-tag>
          <div v-for="rc in row.receipts" :key="rc.id" class="receipt-line">
            <el-link
              v-if="rc.file_url"
              :href="rc.file_url"
              target="_blank"
              type="primary"
              :underline="false"
            >
              {{ rc.receipt_type === 'signed' ? '签收' : '退回补正' }}回执
            </el-link>
            <span v-else>{{ rc.receipt_type === 'signed' ? '签收' : '退回补正' }}回执</span>
            <span class="sub-text">（{{ rc.receipt_date }}）</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="210">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openReceiptDialog(row, 'signed')">
            登记签收
          </el-button>
          <el-button link type="warning" size="small" @click="openReceiptDialog(row, 'returned')">
            退回补正
          </el-button>
          <el-button
            v-if="row.status === 'returned'"
            link
            type="success"
            size="small"
            @click="openSubmissionDialog(row)"
          >重新提交</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!submissions.length" description="尚无提交记录" :image-size="60" />

    <!-- 材料清单 -->
    <el-divider content-position="left">
      材料与版本（{{ materials.length }}）
    </el-divider>
    <el-table :data="materials" size="small" border row-key="id"
              :expand-row-keys="expandedKeys" @expand-change="onExpand">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="version-box">
            <div class="version-head">
              <span>版本记录（{{ row.versions.length }}）</span>
              <el-button type="primary" plain size="small" @click="openVersionDialog(row)">
                上传新版本 / 补录附件
              </el-button>
            </div>
            <el-timeline style="padding: 8px 4px">
              <el-timeline-item
                v-for="v in row.versions"
                :key="v.id"
                :timestamp="`v${v.version_no} · ${v.created_at} · ${v.uploaded_by}`"
                placement="top"
                :type="v.is_final ? 'success' : 'primary'"
              >
                <div class="vline">
                  <el-tag v-if="v.is_final" type="success" size="small" effect="dark">定稿</el-tag>
                  <el-tag v-if="v.is_submitted" type="info" size="small">已提交固定</el-tag>
                  <el-tag v-if="v.is_backfilled" type="warning" size="small">历史补录·待补件</el-tag>
                  <el-link
                    v-if="v.file_url"
                    :href="v.file_url"
                    target="_blank"
                    type="primary"
                    :underline="false"
                    style="margin-left: 6px"
                  >
                    📎 {{ v.file_name }}（{{ formatSize(v.file_size) }}）
                  </el-link>
                  <span v-else class="sub-text" style="margin-left: 6px">暂无附件</span>
                </div>
                <div v-if="v.change_note" class="vnote">{{ v.change_note }}</div>
                <div v-if="v.is_final && v.finalized_by" class="sub-text">
                  定稿确认：{{ v.finalized_by }}<span v-if="v.finalized_at"> · {{ v.finalized_at }}</span>
                </div>

                <!-- 审阅意见 -->
                <div class="reviews">
                  <div v-for="r in v.reviews" :key="r.id" class="review-item">
                    <el-tag :type="reviewTagType(r.result)" size="small">
                      {{ r.result_display }}
                    </el-tag>
                    <b>{{ r.author }}</b>
                    <span class="sub-text">{{ r.created_at }}</span>
                    <div class="review-comment">{{ r.comment }}</div>
                  </div>
                  <el-button link type="primary" size="small" @click="openReviewDialog(v)">
                    + 添加审阅意见
                  </el-button>
                </div>

                <!-- 定稿操作 -->
                <div class="v-actions">
                  <el-button
                    v-if="!v.is_final && v.file && !v.is_submitted"
                    size="small" type="success" plain
                    :loading="v._busy"
                    @click="finalize(row, v)"
                  >确认为定稿版本</el-button>
                  <el-tooltip v-else-if="!v.is_final && !v.file" content="请先补传附件后再定稿" placement="top">
                    <el-button size="small" type="success" plain disabled>确认为定稿版本</el-button>
                  </el-tooltip>
                  <el-tag v-if="v.is_submitted && !v.is_final" type="info" size="small">
                    本版本已随批次提交，不可变更
                  </el-tag>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-if="!row.versions.length" description="尚无版本，请上传第一版" :image-size="50" />
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="材料名称" min-width="200">
        <template #default="{ row }">
          <b>{{ row.name }}</b>
          <el-tag v-if="row.category" size="small" type="info" style="margin-left: 6px">
            {{ row.category }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="定稿" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.final_version_no" type="success" size="small">
            v{{ row.final_version_no }}
          </el-tag>
          <span v-else class="sub-text">未定稿</span>
        </template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">{{ row.versions.length }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="materialTagType(row.status)" size="small" effect="dark">
            {{ row.status_display }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近提交" min-width="180">
        <template #default="{ row }">
          <template v-if="row.latest_submission">
            <div>{{ row.latest_submission.submitted_to }}</div>
            <div class="sub-text">
              {{ row.latest_submission.submit_date }} ·
              v{{ row.latest_submission.version_no }} ·
              {{ row.latest_submission.status_display }}
            </div>
          </template>
          <span v-else class="sub-text">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="notes" label="备注" min-width="120" />
    </el-table>

    <!-- 登记材料 -->
    <el-dialog v-model="materialDialog" title="登记案件材料" width="480px">
      <el-form label-width="90px">
        <el-form-item label="材料名称" required>
          <el-input v-model="materialForm.name" placeholder="如 民事起诉状" />
        </el-form-item>
        <el-form-item label="材料类别">
          <el-select v-model="materialForm.category" allow-create filterable
                     placeholder="起诉状/证据材料/答辩状…" style="width: 100%">
            <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="materialForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="materialDialog = false">取消</el-button>
        <el-button type="primary" @click="createMaterial">保存并开始上传版本</el-button>
      </template>
    </el-dialog>

    <!-- 上传新版本 -->
    <el-dialog v-model="versionDialog" :title="`上传新版本 - ${currentMaterial?.name || ''}`" width="520px">
      <el-alert
        v-if="currentMaterial && currentMaterial.versions.length"
        type="info"
        :closable="false"
        :title="`当前最新版本 v${currentMaterial.versions[0]?.version_no || 0}，本次将自动顺延为 v${(currentMaterial.versions[0]?.version_no || 0) + 1}；多人同时上传各自生成新版本，互不覆盖`"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-else
        type="info" :closable="false"
        title="第一版上传后自动作为初始版本；历史纸质材料也可先登记无附件占位，之后再补录"
        style="margin-bottom: 12px"
      />
      <el-form label-width="90px">
        <el-form-item label="附件文件">
          <input ref="fileInput" type="file" @change="onFileChange" />
          <div v-if="versionForm.fileName" class="sub-text">
            已选择：{{ versionForm.fileName }}（{{ formatSize(versionForm.fileSize) }}）
          </div>
        </el-form-item>
        <el-form-item label="版本说明">
          <el-input v-model="versionForm.change_note"
                    placeholder="如 根据法官意见修改诉讼请求第二项" />
        </el-form-item>
        <el-form-item label="上传人">
          <el-input v-model="versionForm.uploaded_by" />
        </el-form-item>
        <el-form-item v-if="!versionForm.file" label="无附件登记">
          <el-checkbox v-model="versionForm.is_backfilled">
            历史材料补录：暂不上传附件（之后可补传新版本）
          </el-checkbox>
        </el-form-item>
      </el-form>
      <el-alert
        type="warning" :closable="false"
        title="上传失败（文件为空/网络中断）不会留下任何版本或附件记录"
        style="margin-bottom: 8px"
      />
      <template #footer>
        <el-button @click="versionDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="uploadVersion">上传</el-button>
      </template>
    </el-dialog>

    <!-- 审阅意见 -->
    <el-dialog v-model="reviewDialog" title="添加审阅意见" width="480px">
      <el-form label-width="90px">
        <el-form-item label="审阅人">
          <el-input v-model="reviewForm.author" />
        </el-form-item>
        <el-form-item label="结论">
          <el-radio-group v-model="reviewForm.result">
            <el-radio value="comment">意见</el-radio>
            <el-radio value="revise">需修改</el-radio>
            <el-radio value="approve">同意定稿</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="意见内容" required>
          <el-input v-model="reviewForm.comment" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addReview">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建提交批次 -->
    <el-dialog v-model="submissionDialog" width="720px"
               :title="resubmitSource ? `补正后重新提交（原批次 #${resubmitSource.id}）` : '新建提交批次'">
      <el-alert v-if="resubmitSource" type="warning" :closable="false" style="margin-bottom: 12px">
        <template #title>
          原批次（{{ resubmitSource.submit_date }} 提交至 {{ resubmitSource.submitted_to }}）已被退回补正。
          请先上传补正版并定稿，再在此选择新版本重新提交；原批次记录与退回回执将完整保留。
        </template>
      </el-alert>
      <el-form label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="接收对象" required>
              <el-input v-model="submissionForm.submitted_to"
                        placeholder="如 朝阳区人民法院立案庭 / 对方代理人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="接收人">
              <el-input v-model="submissionForm.receiver_name" placeholder="窗口/签收人" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="提交方式">
              <el-select v-model="submissionForm.method" style="width: 100%">
                <el-option label="立案/诉讼窗口" value="window" />
                <el-option label="网上平台" value="online" />
                <el-option label="邮寄" value="post" />
                <el-option label="当面递交" value="hand" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="提交日期" required>
              <el-date-picker v-model="submissionForm.submit_date" type="date"
                              value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="经办人">
              <el-input v-model="submissionForm.created_by" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="submissionForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <el-divider style="margin: 6px 0">提交清单（仅可选择已定稿且有附件的版本；提交后版本即被固定）</el-divider>
      <el-table :data="selectableRows" size="small" max-height="260"
                @selection-change="onSelectionChange" ref="subTable">
        <el-table-column type="selection" width="45" />
        <el-table-column prop="material_name" label="材料" min-width="180" />
        <el-table-column label="选用版本" width="200">
          <template #default="{ row }">
            <el-select v-model="row.version_id" size="small" style="width: 100%">
              <el-option
                v-for="v in row.finalVersions"
                :key="v.id"
                :label="`v${v.version_no}${v.is_backfilled ? '（无附件·不可选）' : ''}${v.is_submitted ? '（曾提交）' : ''}`"
                :value="v.id"
                :disabled="!v.file"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="份数" width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.copies" :min="1" :max="20" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="页数" width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.pages" :min="1" size="small"
                             :placeholder="'—'" controls-position="right" />
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="submissionDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createSubmission">
          固定清单并提交
        </el-button>
      </template>
    </el-dialog>

    <!-- 回执 -->
    <el-dialog v-model="receiptDialog" width="520px"
               :title="receiptForm.receipt_type === 'signed' ? '登记签收回执' : '登记退回补正通知'">
      <el-form label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="回执日期" required>
              <el-date-picker v-model="receiptForm.receipt_date" type="date"
                              value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="签收编号">
              <el-input v-model="receiptForm.receipt_no" placeholder="如 立收字第xxx号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="签收/经办人">
          <el-input v-model="receiptForm.receiver_name" />
        </el-form-item>
        <el-form-item label="回执扫描件">
          <input type="file" @change="onReceiptFileChange" />
          <div v-if="receiptForm.fileName" class="sub-text">已选择：{{ receiptForm.fileName }}</div>
        </el-form-item>
        <el-form-item :label="receiptForm.receipt_type === 'signed' ? '说明' : '补正事项'"
                      :required="receiptForm.receipt_type === 'returned'">
          <el-input v-model="receiptForm.note" type="textarea" :rows="3"
                    :placeholder="receiptForm.receipt_type === 'returned'
                      ? '请写明需要补正的内容，以便补正后重新提交'
                      : '签收情况说明'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="receiptDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addReceipt">保存回执</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import api from '../api'

const props = defineProps({
  caseId: { type: [String, Number], required: true },
  materials: { type: Array, default: () => [] },
  submissions: { type: Array, default: () => [] },
})
const emit = defineEmits(['reload'])

const categoryOptions = ['起诉状', '答辩状', '上诉状', '证据材料', '代理词',
  '辩护意见', '申请书', '委托手续', '仲裁申请', '其他']

const OPERATOR_KEY = 'lawfirm_operator'
const operator = ref(localStorage.getItem(OPERATOR_KEY) || '')
function saveOperator() {
  localStorage.setItem(OPERATOR_KEY, operator.value.trim())
}

const expandedKeys = ref([])
function onExpand(row, expandedRows) {
  expandedKeys.value = expandedRows.map((r) => r.id)
}

/* ---------- 登记材料 ---------- */
const materialDialog = ref(false)
const materialForm = reactive({ name: '', category: '', notes: '' })
const newMaterialId = ref(null)

function openMaterialDialog() {
  Object.assign(materialForm, { name: '', category: '', notes: '' })
  newMaterialId.value = null
  materialDialog.value = true
}

async function createMaterial() {
  if (!materialForm.name) {
    ElMessage.warning('请填写材料名称')
    return
  }
  saving.value = true
  try {
    const res = await api.post('/materials/', {
      case: Number(props.caseId), ...materialForm,
    })
    newMaterialId.value = res.data.id
    materialDialog.value = false
    ElMessage.success('材料已登记，请上传第一版')
    emit('reload')
    // 直接打开上传框
    setTimeout(() => {
      const row = { ...res.data, versions: [] }
      openVersionDialog(row)
    }, 400)
  } finally {
    saving.value = false
  }
}

/* ---------- 上传版本 ---------- */
const versionDialog = ref(false)
const fileInput = ref(null)
const currentMaterial = ref(null)
const versionForm = reactive({
  file: null, fileName: '', fileSize: 0, change_note: '',
  uploaded_by: '', is_backfilled: false,
})
const saving = ref(false)

function openVersionDialog(row) {
  currentMaterial.value = row
  Object.assign(versionForm, {
    file: null, fileName: '', fileSize: 0, change_note: '',
    uploaded_by: operator.value || '', is_backfilled: false,
  })
  versionDialog.value = true
}

function onFileChange(e) {
  const f = e.target.files[0]
  if (!f) return
  if (f.size === 0) {
    ElMessage.error('文件内容为空，无法上传')
    e.target.value = ''
    return
  }
  if (f.size > 100 * 1024 * 1024) {
    ElMessage.error('附件不能超过 100MB')
    e.target.value = ''
    return
  }
  versionForm.file = f
  versionForm.fileName = f.name
  versionForm.fileSize = f.size
}

async function uploadVersion() {
  const m = currentMaterial.value
  if (!m) return
  if (!versionForm.file && !versionForm.is_backfilled) {
    ElMessage.warning('请选择附件；历史补录可勾选“暂不上传附件”')
    return
  }
  if (!versionForm.uploaded_by) {
    ElMessage.warning('请填写上传人')
    return
  }
  const fd = new FormData()
  fd.append('material', m.id)
  fd.append('uploaded_by', versionForm.uploaded_by)
  fd.append('change_note', versionForm.change_note)
  fd.append('is_backfilled', versionForm.is_backfilled ? 'true' : 'false')
  if (versionForm.file) fd.append('file', versionForm.file)
  saving.value = true
  try {
    const res = await api.post('/material-versions/', fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
    ElMessage.success(`v${res.data.version_no} 已上传`)
    versionDialog.value = false
    if (!expandedKeys.value.includes(m.id)) expandedKeys.value.push(m.id)
    emit('reload')
  } finally {
    saving.value = false
  }
}

/* ---------- 定稿 ---------- */
async function finalize(row, v) {
  if (!operator.value) {
    ElMessage.warning('请先在顶部填写当前操作人（定稿确认人）')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将「${row.name} v${v.version_no}」定为定稿版本？` +
      `提交后所用版本将被固定；已有提交被退回时，定稿将自动前移到补正版。`,
      '定稿确认', { type: 'warning', confirmButtonText: '确认定稿', cancelButtonText: '取消' })
  } catch {
    return
  }
  saving.value = true
  try {
    await api.post(`/material-versions/${v.id}/finalize/`, { operator: operator.value })
    ElMessage.success('定稿已确认')
    emit('reload')
  } finally {
    saving.value = false
  }
}

/* ---------- 审阅意见 ---------- */
const reviewDialog = ref(false)
const currentVersion = ref(null)
const reviewForm = reactive({ author: '', result: 'comment', comment: '' })

function openReviewDialog(v) {
  currentVersion.value = v
  Object.assign(reviewForm, {
    author: operator.value || '', result: 'comment', comment: '',
  })
  reviewDialog.value = true
}

async function addReview() {
  if (!reviewForm.author || !reviewForm.comment) {
    ElMessage.warning('审阅人与意见内容必填')
    return
  }
  saving.value = true
  try {
    await api.post('/material-reviews/', { version: currentVersion.value.id, ...reviewForm })
    ElMessage.success('审阅意见已记录（只追加，不可修改）')
    reviewDialog.value = false
    emit('reload')
  } finally {
    saving.value = false
  }
}

/* ---------- 提交批次 ---------- */
const submissionDialog = ref(false)
const resubmitSource = ref(null)
const subTable = ref(null)
const submissionForm = reactive({
  submitted_to: '', receiver_name: '', method: 'window',
  submit_date: new Date().toISOString().slice(0, 10),
  created_by: '', note: '',
})
const selectedRows = ref([])
const selectableRows = ref([])

const finalMaterials = computed(() =>
  props.materials.map((m) => {
    const finals = [...m.versions].filter((v) => v.is_final)
    return {
      material_id: m.id,
      material_name: m.name,
      finalVersions: m.versions.filter((v) => v.is_final && v.file),
      version_id: finals.find((v) => v.file)?.id
        || m.versions.find((v) => v.is_final && v.file)?.id || null,
      copies: 1,
      pages: null,
    }
  }).filter((r) => r.finalVersions.length))

function openSubmissionDialog(source = null) {
  resubmitSource.value = source
  Object.assign(submissionForm, {
    submitted_to: source?.submitted_to || '',
    receiver_name: source?.receiver_name || '',
    method: source?.method || 'window',
    submit_date: new Date().toISOString().slice(0, 10),
    created_by: operator.value || '',
    note: source ? '退回补正后重新提交' : '',
  })
  selectableRows.value = finalMaterials.value.map((r) => ({ ...r }))
  selectedRows.value = []
  submissionDialog.value = true
}

function onSelectionChange(rows) {
  selectedRows.value = rows
}

async function createSubmission() {
  if (!submissionForm.submitted_to || !submissionForm.submit_date) {
    ElMessage.warning('接收对象与提交日期必填')
    return
  }
  if (!submissionForm.created_by) {
    ElMessage.warning('请填写经办人')
    return
  }
  const items = selectedRows.value.map((r) => ({
    version_id: r.version_id,
    copies: r.copies,
    pages: r.pages || null,
  }))
  if (!items.length) {
    ElMessage.warning('请至少勾选一个定稿版本加入清单')
    return
  }
  saving.value = true
  try {
    await api.post('/submissions/', {
      case: Number(props.caseId),
      ...submissionForm,
      resubmitted_from: resubmitSource.value?.id || null,
      items,
    })
    ElMessage.success('提交批次已建立，清单与版本已固定')
    submissionDialog.value = false
    emit('reload')
  } finally {
    saving.value = false
  }
}

/* ---------- 回执 ---------- */
const receiptDialog = ref(false)
const receiptTarget = ref(null)
const receiptForm = reactive({
  receipt_type: 'signed', receipt_date: '', receipt_no: '',
  receiver_name: '', note: '', file: null, fileName: '',
})

function openReceiptDialog(submission, type) {
  receiptTarget.value = submission
  Object.assign(receiptForm, {
    receipt_type: type,
    receipt_date: new Date().toISOString().slice(0, 10),
    receipt_no: '', receiver_name: submission.receiver_name || '',
    note: type === 'returned' ? '' : '',
    file: null, fileName: '',
  })
  receiptDialog.value = true
}

function onReceiptFileChange(e) {
  const f = e.target.files[0]
  if (!f) return
  if (f.size > 100 * 1024 * 1024) {
    ElMessage.error('附件不能超过 100MB')
    e.target.value = ''
    return
  }
  receiptForm.file = f
  receiptForm.fileName = f.name
}

async function addReceipt() {
  if (!receiptForm.receipt_date) {
    ElMessage.warning('请填写回执日期')
    return
  }
  if (receiptForm.receipt_type === 'returned' && !receiptForm.note) {
    ElMessage.warning('退回补正必须填写补正事项')
    return
  }
  const fd = new FormData()
  fd.append('submission', receiptTarget.value.id)
  fd.append('receipt_type', receiptForm.receipt_type)
  fd.append('receipt_date', receiptForm.receipt_date)
  fd.append('receipt_no', receiptForm.receipt_no)
  fd.append('receiver_name', receiptForm.receiver_name)
  fd.append('note', receiptForm.note)
  if (receiptForm.file) fd.append('file', receiptForm.file)
  saving.value = true
  try {
    await api.post('/submission-receipts/', fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
    ElMessage.success(receiptForm.receipt_type === 'signed' ? '签收回执已登记' : '退回补正已登记')
    receiptDialog.value = false
    emit('reload')
  } finally {
    saving.value = false
  }
}

/* ---------- 展示工具 ---------- */
const METHOD_MAP = { window: '窗口', online: '网上平台', post: '邮寄', hand: '当面递交', other: '其他' }
const methodText = (m) => METHOD_MAP[m] || m
const formatSize = (n) => {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
const materialTagType = (s) => (
  { signed: 'success', submitted: 'primary', returned: 'danger', finalized: 'warning' }[s] || 'info')
const submissionTagType = (s) => (
  { signed: 'success', returned: 'danger' }[s] || 'primary')
const reviewTagType = (r) => (
  { approve: 'success', revise: 'danger' }[r] || 'info')
</script>

<style scoped>
.tab-bar { display: flex; align-items: center; margin-bottom: 12px; }
.sub-text { color: #909399; font-size: 12px; }
.version-box { padding: 4px 20px; background: #fafbfc; }
.version-head { display: flex; justify-content: space-between; align-items: center; }
.vline { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.vnote { margin: 4px 0; }
.reviews { margin: 6px 0; padding-left: 8px; border-left: 3px solid #e4e7ed; }
.review-item { margin-bottom: 6px; }
.review-comment { margin: 2px 0 0 60px; color: #444; }
.v-actions { margin-top: 4px; }
.receipt-line { margin-top: 2px; }
</style>
