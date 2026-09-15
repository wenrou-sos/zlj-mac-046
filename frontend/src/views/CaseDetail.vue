<template>
  <div v-loading="loading">
    <template v-if="caseData.id">
      <!-- 头部 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <div class="head">
          <div>
            <div class="title-row">
              <span class="title">{{ caseData.title }}</span>
              <el-tag size="small" effect="dark">{{ caseData.stage_display }}</el-tag>
              <el-tag size="small" type="info">{{ caseData.case_type_display }}</el-tag>
              <el-tag v-if="caseData.archive?.is_sealed" size="small" type="success" effect="dark">
                已封存 v{{ caseData.archive.sealed_version }}
              </el-tag>
              <el-tag v-else-if="caseData.archive?.current_status === 'submitted'" size="small" type="warning" effect="dark">
                待复核 v{{ caseData.archive.current_version }}
              </el-tag>
            </div>
            <div class="sub">{{ caseData.case_number }}</div>
          </div>
          <el-button @click="$router.push('/cases')">返回列表</el-button>
        </div>
        <el-descriptions :column="4" border size="small" style="margin-top: 12px">
          <el-descriptions-item label="案由">{{ caseData.cause || '-' }}</el-descriptions-item>
          <el-descriptions-item label="受理法院/机构">{{ caseData.court || '-' }}</el-descriptions-item>
          <el-descriptions-item label="立案日期">{{ caseData.filed_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="标的额">
            {{ caseData.amount ? `¥${Number(caseData.amount).toLocaleString()}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="案情简介" :span="4">
            {{ caseData.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-alert
        v-if="locked"
        type="success" :closable="false" show-icon
        title="本案卷宗已封存，日常编辑与删除已锁定；再审或补充材料请在「结案归档」页签申请重开。"
        style="margin-bottom: 16px"
      />

      <el-card shadow="never">
        <el-tabs v-model="tab">
          <!-- 结案归档 -->
          <el-tab-pane name="archive">
            <template #label>
              <span>结案归档
                <el-badge v-if="caseData.archive?.current_status === 'submitted'"
                  is-dot type="warning" />
              </span>
            </template>
            <ArchivePanel :case-data="caseData" @refresh="load" />
          </el-tab-pane>

          <!-- 当事人 -->
          <el-tab-pane :label="`当事人 (${caseData.case_parties.length})`" name="parties">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="openPartyDialog">添加当事人</el-button>
            </div>
            <el-table :data="caseData.case_parties" size="small">
              <el-table-column label="姓名/名称" min-width="180">
                <template #default="{ row }">{{ row.party.name }}</template>
              </el-table-column>
              <el-table-column prop="role_display" label="诉讼地位" width="110" />
              <el-table-column label="本所客户" width="90" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_client" type="success" size="small">是</el-tag>
                  <span v-else>否</span>
                </template>
              </el-table-column>
              <el-table-column label="证件号" min-width="170">
                <template #default="{ row }">{{ row.party.id_number || '-' }}</template>
              </el-table-column>
              <el-table-column label="电话" width="130">
                <template #default="{ row }">{{ row.party.phone || '-' }}</template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-popconfirm v-if="!locked" title="确定从本案移除该当事人？" @confirm="removeParty(row)">
                    <template #reference>
                      <el-button link type="danger" size="small">移除</el-button>
                    </template>
                  </el-popconfirm>
                  <span v-else class="readonly-tip">已封存</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 承办律师 -->
          <el-tab-pane :label="`承办律师 (${caseData.case_lawyers.length})`" name="lawyers">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="lawyerDialog = true">添加承办律师</el-button>
            </div>
            <el-table :data="caseData.case_lawyers" size="small">
              <el-table-column label="姓名" min-width="120">
                <template #default="{ row }">{{ row.lawyer.name }}</template>
              </el-table-column>
              <el-table-column prop="role_display" label="承办角色" width="110" />
              <el-table-column label="执业证号" min-width="170">
                <template #default="{ row }">{{ row.lawyer.bar_number }}</template>
              </el-table-column>
              <el-table-column label="电话" width="140">
                <template #default="{ row }">{{ row.lawyer.phone || '-' }}</template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-popconfirm v-if="!locked" title="确定移除该承办律师？" @confirm="removeLawyer(row)">
                    <template #reference>
                      <el-button link type="danger" size="small">移除</el-button>
                    </template>
                  </el-popconfirm>
                  <span v-else class="readonly-tip">已封存</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 诉讼阶段 -->
          <el-tab-pane label="诉讼阶段" name="stages">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="stageDialog = true">记录阶段流转</el-button>
            </div>
            <el-timeline style="padding-left: 4px; margin-top: 8px">
              <el-timeline-item
                v-for="log in [...caseData.stage_logs].reverse()"
                :key="log.id"
                :timestamp="log.log_date"
                placement="top"
                :type="log.stage === caseData.stage ? 'primary' : ''"
              >
                <b>{{ log.stage_display }}</b>
                <span v-if="log.stage === caseData.stage" class="current">（当前阶段）</span>
                <div class="sub">{{ log.notes }}</div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-if="!caseData.stage_logs.length" description="暂无阶段记录" :image-size="60" />
          </el-tab-pane>

          <!-- 开庭安排 -->
          <el-tab-pane :label="`开庭安排 (${caseData.hearings.length})`" name="hearings">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="hearingDialog = true">添加开庭</el-button>
            </div>
            <el-table :data="caseData.hearings" size="small">
              <el-table-column prop="hearing_time" label="开庭时间" width="160" />
              <el-table-column prop="location" label="地点" min-width="200" />
              <el-table-column prop="judge" label="法官/仲裁员" width="120" />
              <el-table-column prop="notes" label="备注" min-width="160" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-popconfirm v-if="!locked" title="确定删除该开庭安排？" @confirm="del('/hearings/', row.id)">
                    <template #reference>
                      <el-button link type="danger" size="small">删除</el-button>
                    </template>
                  </el-popconfirm>
                  <span v-else class="readonly-tip">已封存</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 材料 -->
          <el-tab-pane :label="`案件材料 (${caseData.materials.length})`" name="materials">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="materialDialog = true">登记材料</el-button>
            </div>
            <el-table :data="caseData.materials" size="small">
              <el-table-column prop="name" label="材料名称" min-width="200" />
              <el-table-column prop="submitted_to" label="提交对象" min-width="150" />
              <el-table-column prop="submit_date" label="提交日期" width="110">
                <template #default="{ row }">{{ row.submit_date || '-' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="130">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.status"
                    size="small"
                    :disabled="locked"
                    @change="(v) => updateMaterialStatus(row, v)"
                  >
                    <el-option label="待提交" value="pending" />
                    <el-option label="已提交" value="submitted" />
                    <el-option label="已签收" value="accepted" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column prop="notes" label="备注" min-width="140" />
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-popconfirm v-if="!locked" title="确定删除该材料记录？" @confirm="del('/materials/', row.id)">
                    <template #reference>
                      <el-button link type="danger" size="small">删除</el-button>
                    </template>
                  </el-popconfirm>
                  <span v-else class="readonly-tip">已封存</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 期限 -->
          <el-tab-pane :label="`期限管理 (${pendingDeadlines.length})`" name="deadlines">
            <div class="tab-bar">
              <el-button type="primary" size="small" :disabled="locked" @click="deadlineDialog = true">添加期限</el-button>
            </div>
            <el-table :data="caseData.deadlines" size="small">
              <el-table-column prop="title" label="事项" min-width="180" />
              <el-table-column prop="deadline_type_display" label="类型" width="120" />
              <el-table-column prop="due_date" label="截止日期" width="110" />
              <el-table-column label="剩余" width="100">
                <template #default="{ row }">
                  <el-tag v-if="!row.is_done" :type="daysType(row.days_left)" size="small" effect="dark">
                    {{ daysText(row.days_left) }}
                  </el-tag>
                  <el-tag v-else type="info" size="small">已办结</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="notes" label="备注" min-width="160" />
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <template v-if="!locked">
                    <el-button
                      v-if="!row.is_done"
                      link
                      type="success"
                      size="small"
                      @click="markDone(row)"
                    >办结</el-button>
                    <el-popconfirm title="确定删除该期限？" @confirm="del('/deadlines/', row.id)">
                      <template #reference>
                        <el-button link type="danger" size="small">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </template>
                  <span v-else class="readonly-tip">已封存</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>

    <!-- 添加当事人对话框 -->
    <el-dialog v-model="partyDialog" title="添加当事人" width="560px">
      <el-alert
        type="warning"
        :closable="false"
        title="保存前将自动进行利益冲突预检"
        style="margin-bottom: 12px"
      />
      <el-form label-width="100px">
        <el-form-item label="当事人" required>
          <el-select
            v-model="partyForm.party_id"
            filterable
            remote
            :remote-method="searchParties"
            :loading="partySearching"
            placeholder="输入姓名/名称检索"
            style="width: 100%"
          >
            <el-option v-for="p in partyOptions" :key="p.id" :label="p.name" :value="p.id">
              <span>{{ p.name }}</span>
              <span class="opt-sub">{{ p.party_type_display }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button link type="primary" @click="newPartyDialog = true">没有？新建当事人档案</el-button>
        </el-form-item>
        <el-form-item label="诉讼地位">
          <el-select v-model="partyForm.role" style="width: 100%">
            <el-option v-for="(label, key) in roleMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="本所客户">
          <el-switch v-model="partyForm.is_client" active-text="是" inactive-text="否" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="partyDialog = false">取消</el-button>
        <el-button type="primary" :loading="partySaving" @click="addParty">冲突预检并保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建当事人(内嵌) -->
    <el-dialog v-model="newPartyDialog" title="新建当事人档案" width="480px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="姓名/名称" required>
          <el-input v-model="newParty.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="newParty.party_type">
            <el-radio value="person">自然人</el-radio>
            <el-radio value="org">法人/组织</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="证件号">
          <el-input v-model="newParty.id_number" placeholder="身份证号/统一社会信用代码" />
        </el-form-item>
        <el-form-item label="电话">
          <el-input v-model="newParty.phone" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="newParty.address" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newPartyDialog = false">取消</el-button>
        <el-button type="primary" @click="createParty">保存</el-button>
      </template>
    </el-dialog>

    <!-- 添加律师对话框 -->
    <el-dialog v-model="lawyerDialog" title="添加承办律师" width="440px">
      <el-form label-width="90px">
        <el-form-item label="律师" required>
          <el-select v-model="lawyerForm.lawyer_id" filterable style="width: 100%">
            <el-option v-for="l in allLawyers" :key="l.id" :label="`${l.name}(${l.title_display})`" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="承办角色">
          <el-radio-group v-model="lawyerForm.role">
            <el-radio value="lead">主办律师</el-radio>
            <el-radio value="assist">协办律师</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="lawyerDialog = false">取消</el-button>
        <el-button type="primary" @click="addLawyer">保存</el-button>
      </template>
    </el-dialog>

    <!-- 阶段流转对话框 -->
    <el-dialog v-model="stageDialog" title="记录阶段流转" width="440px">
      <el-form label-width="90px">
        <el-form-item label="流转至">
          <el-select v-model="stageForm.stage" style="width: 100%">
            <el-option v-for="(label, key) in stageMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="stageForm.log_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="stageForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="保存后案件当前阶段将同步更新" />
      <template #footer>
        <el-button @click="stageDialog = false">取消</el-button>
        <el-button type="primary" @click="addStageLog">保存</el-button>
      </template>
    </el-dialog>

    <!-- 开庭对话框 -->
    <el-dialog v-model="hearingDialog" title="添加开庭安排" width="440px">
      <el-form label-width="90px">
        <el-form-item label="开庭时间" required>
          <el-date-picker
            v-model="hearingForm.hearing_time"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="地点" required>
          <el-input v-model="hearingForm.location" placeholder="如 朝阳区人民法院第12法庭" />
        </el-form-item>
        <el-form-item label="法官/仲裁员">
          <el-input v-model="hearingForm.judge" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="hearingForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="hearingDialog = false">取消</el-button>
        <el-button type="primary" @click="addHearing">保存</el-button>
      </template>
    </el-dialog>

    <!-- 材料对话框 -->
    <el-dialog v-model="materialDialog" title="登记案件材料" width="440px">
      <el-form label-width="90px">
        <el-form-item label="材料名称" required>
          <el-input v-model="materialForm.name" />
        </el-form-item>
        <el-form-item label="提交对象">
          <el-input v-model="materialForm.submitted_to" placeholder="如 朝阳区人民法院" />
        </el-form-item>
        <el-form-item label="提交日期">
          <el-date-picker v-model="materialForm.submit_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="materialForm.status" style="width: 100%">
            <el-option label="待提交" value="pending" />
            <el-option label="已提交" value="submitted" />
            <el-option label="已签收" value="accepted" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="materialForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="materialDialog = false">取消</el-button>
        <el-button type="primary" @click="addMaterial">保存</el-button>
      </template>
    </el-dialog>

    <!-- 期限对话框 -->
    <el-dialog v-model="deadlineDialog" title="添加期限提醒" width="440px">
      <el-form label-width="90px">
        <el-form-item label="事项" required>
          <el-input v-model="deadlineForm.title" placeholder="如 举证期限届满" />
        </el-form-item>
        <el-form-item label="期限类型">
          <el-select v-model="deadlineForm.deadline_type" style="width: 100%">
            <el-option v-for="(label, key) in deadlineTypeMap" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止日期" required>
          <el-date-picker v-model="deadlineForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="提前提醒">
          <el-input-number v-model="deadlineForm.remind_days" :min="0" :max="90" />
          <span class="sub" style="margin-left: 8px">天</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="deadlineForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deadlineDialog = false">取消</el-button>
        <el-button type="primary" @click="addDeadline">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import ArchivePanel from '../components/ArchivePanel.vue'

const route = useRoute()
const caseId = route.params.id

const stageMap = { filing: '立案', first: '一审', second: '二审', retrial: '再审', enforcement: '执行', closed: '结案' }
const roleMap = {
  plaintiff: '原告', defendant: '被告', third: '第三人', appellant: '上诉人',
  appellee: '被上诉人', applicant: '申请执行人', respondent: '被执行人',
  suspect: '犯罪嫌疑人', victim: '被害人',
}
const deadlineTypeMap = {
  appeal: '上诉期限', evidence: '举证期限', defense: '答辩期限', hearing: '开庭',
  payment: '缴费期限', retrial: '再审申请期限', enforcement: '申请执行期限', other: '其他',
}

const loading = ref(false)
const caseData = ref({ case_parties: [], case_lawyers: [], stage_logs: [], hearings: [], materials: [], deadlines: [], archive_versions: [], reopen_requests: [], archive: {} })
const tab = ref(route.query.tab === 'archive' ? 'archive' : 'parties')
const locked = computed(() => !!caseData.value.archive?.is_sealed)

const partyDialog = ref(false)
const newPartyDialog = ref(false)
const lawyerDialog = ref(false)
const stageDialog = ref(false)
const hearingDialog = ref(false)
const materialDialog = ref(false)
const deadlineDialog = ref(false)

const partyOptions = ref([])
const partySearching = ref(false)
const partySaving = ref(false)
const allLawyers = ref([])

const partyForm = reactive({ party_id: null, role: 'plaintiff', is_client: false })
const newParty = reactive({ name: '', party_type: 'person', id_number: '', phone: '', address: '' })
const lawyerForm = reactive({ lawyer_id: null, role: 'lead' })
const stageForm = reactive({ stage: '', log_date: '', notes: '' })
const hearingForm = reactive({ hearing_time: '', location: '', judge: '', notes: '' })
const materialForm = reactive({ name: '', submitted_to: '', submit_date: null, status: 'pending', notes: '' })
const deadlineForm = reactive({ title: '', deadline_type: 'other', due_date: '', remind_days: 7, notes: '' })

const pendingDeadlines = computed(() => caseData.value.deadlines.filter((d) => !d.is_done))

const daysType = (n) => (n < 0 ? 'danger' : n <= 7 ? 'warning' : 'success')
const daysText = (n) => (n < 0 ? `逾期${-n}天` : n === 0 ? '今天' : `${n}天`)

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/cases/${caseId}/`)
    caseData.value = res.data
  } finally {
    loading.value = false
  }
}

/* ---------- 当事人 ---------- */
function openPartyDialog() {
  partyForm.party_id = null
  partyForm.role = 'plaintiff'
  partyForm.is_client = false
  searchParties('')
  partyDialog.value = true
}

async function searchParties(kw) {
  partySearching.value = true
  try {
    const res = await api.get('/parties/', { params: { search: kw || '' } })
    partyOptions.value = res.data
  } finally {
    partySearching.value = false
  }
}

async function createParty() {
  if (!newParty.name) {
    ElMessage.warning('请填写姓名/名称')
    return
  }
  const res = await api.post('/parties/', newParty)
  ElMessage.success('当事人档案已建立')
  newPartyDialog.value = false
  Object.assign(newParty, { name: '', party_type: 'person', id_number: '', phone: '', address: '' })
  await searchParties('')
  partyForm.party_id = res.data.id
}

async function addParty() {
  if (!partyForm.party_id) {
    ElMessage.warning('请选择当事人')
    return
  }
  partySaving.value = true
  try {
    // 1. 利益冲突预检
    const check = await api.post(`/cases/${caseId}/conflict-check/`, {
      party_id: partyForm.party_id,
      is_client: partyForm.is_client,
    })
    const { has_conflict, conflicts } = check.data
    if (conflicts.length) {
      const html = conflicts
        .map((c) => `<p style="color:${{ high: '#f56c6c', medium: '#e6a23c' }[c.level] || '#909399'}">【${{ high: '高风险', medium: '注意', low: '提示' }[c.level]}】${c.message}</p>`)
        .join('')
      if (has_conflict) {
        await ElMessageBox.alert(html, '利益冲突预检未通过', {
          dangerouslyUseHTMLString: true,
          confirmButtonText: '知道了',
          type: 'error',
        })
        return
      }
      await ElMessageBox.confirm(html, '冲突预检提示', {
        dangerouslyUseHTMLString: true,
        confirmButtonText: '仍要添加',
        cancelButtonText: '取消',
        type: 'warning',
      })
    }
    // 2. 保存
    await api.post('/case-parties/', { case: Number(caseId), ...partyForm })
    ElMessage.success('当事人已添加')
    partyDialog.value = false
    load()
  } catch (e) {
    // 用户取消，或接口错误（拦截器已提示）
  } finally {
    partySaving.value = false
  }
}

async function removeParty(row) {
  await api.delete(`/case-parties/${row.id}/`)
  ElMessage.success('已移除')
  load()
}

/* ---------- 律师 ---------- */
async function addLawyer() {
  if (!lawyerForm.lawyer_id) {
    ElMessage.warning('请选择律师')
    return
  }
  await api.post('/case-lawyers/', { case: Number(caseId), ...lawyerForm })
  ElMessage.success('承办律师已添加')
  lawyerDialog.value = false
  load()
}

async function removeLawyer(row) {
  await api.delete(`/case-lawyers/${row.id}/`)
  ElMessage.success('已移除')
  load()
}

/* ---------- 阶段 ---------- */
async function addStageLog() {
  if (!stageForm.stage || !stageForm.log_date) {
    ElMessage.warning('请选择阶段和日期')
    return
  }
  await api.post('/stage-logs/', { case: Number(caseId), ...stageForm })
  await api.patch(`/cases/${caseId}/`, { stage: stageForm.stage })
  ElMessage.success('阶段已更新')
  stageDialog.value = false
  Object.assign(stageForm, { stage: '', log_date: '', notes: '' })
  load()
}

/* ---------- 开庭 ---------- */
async function addHearing() {
  if (!hearingForm.hearing_time || !hearingForm.location) {
    ElMessage.warning('开庭时间和地点必填')
    return
  }
  await api.post('/hearings/', { case: Number(caseId), ...hearingForm })
  ElMessage.success('开庭安排已添加')
  hearingDialog.value = false
  Object.assign(hearingForm, { hearing_time: '', location: '', judge: '', notes: '' })
  load()
}

/* ---------- 材料 ---------- */
async function addMaterial() {
  if (!materialForm.name) {
    ElMessage.warning('材料名称必填')
    return
  }
  await api.post('/materials/', { case: Number(caseId), ...materialForm })
  ElMessage.success('材料已登记')
  materialDialog.value = false
  Object.assign(materialForm, { name: '', submitted_to: '', submit_date: null, status: 'pending', notes: '' })
  load()
}

async function updateMaterialStatus(row, status) {
  const payload = { status }
  if (status !== 'pending' && !row.submit_date) {
    payload.submit_date = new Date().toISOString().slice(0, 10)
  }
  await api.patch(`/materials/${row.id}/`, payload)
  ElMessage.success('状态已更新')
  load()
}

/* ---------- 期限 ---------- */
async function addDeadline() {
  if (!deadlineForm.title || !deadlineForm.due_date) {
    ElMessage.warning('事项和截止日期必填')
    return
  }
  await api.post('/deadlines/', { case: Number(caseId), ...deadlineForm })
  ElMessage.success('期限已添加')
  deadlineDialog.value = false
  Object.assign(deadlineForm, { title: '', deadline_type: 'other', due_date: '', remind_days: 7, notes: '' })
  load()
}

async function markDone(row) {
  await api.patch(`/deadlines/${row.id}/`, { is_done: true })
  ElMessage.success('已办结')
  load()
}

/* ---------- 通用删除 ---------- */
async function del(url, id) {
  await api.delete(`${url}${id}/`)
  ElMessage.success('已删除')
  load()
}

onMounted(async () => {
  load()
  const res = await api.get('/lawyers/')
  allLawyers.value = res.data
})
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; }
.title-row { display: flex; align-items: center; gap: 8px; }
.title { font-size: 18px; font-weight: 600; }
.sub { color: #999; font-size: 13px; margin-top: 4px; }
.tab-bar { margin-bottom: 12px; }
.opt-sub { float: right; color: #999; font-size: 12px; }
.current { color: #409eff; font-size: 13px; }
.readonly-tip { color: #bbb; font-size: 12px; }
</style>
