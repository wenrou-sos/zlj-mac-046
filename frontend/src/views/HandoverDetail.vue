<template>
  <div v-loading="loading">
    <template v-if="h.id">
      <!-- 头部 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <div class="head">
          <div>
            <div class="title-row">
              <router-link :to="`/cases/${h.case}`" class="title">{{ h.case_title }}</router-link>
              <el-tag :type="statusType(h.status)" size="small" effect="dark">{{ h.status_display }}</el-tag>
              <el-tag v-if="stale && h.status === 'pending'" type="danger" size="small" effect="dark">
                清单已过期，请先补入最新待办
              </el-tag>
            </div>
            <div class="sub">{{ h.case_number }}</div>
          </div>
          <el-button @click="$router.back()">返回</el-button>
        </div>

        <el-descriptions :column="3" border size="small" style="margin-top: 12px">
          <el-descriptions-item label="交出人">
            <b :class="{ actor: actorId === h.from_lawyer }">{{ h.from_lawyer_name }}</b>
          </el-descriptions-item>
          <el-descriptions-item label="接收人">
            <b :class="{ actor: actorId === h.to_lawyer }">{{ h.to_lawyer_name }}</b>
          </el-descriptions-item>
          <el-descriptions-item label="交接原因">{{ h.reason || '律师离岗/更换主办' }}</el-descriptions-item>
          <el-descriptions-item label="清单刷新时间">{{ fmt(h.last_refreshed_at) }}</el-descriptions-item>
          <el-descriptions-item label="提交核对时间">{{ fmt(h.submitted_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ fmt(h.completed_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="h.returned_reason" label="退回原因" :span="3">
            <span style="color: #f56c6c">{{ h.returned_reason }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="h.cancel_reason" label="取消原因" :span="3">
            {{ h.cancel_reason }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 当前操作身份（本系统无登录，按实际操作律师区分权限） -->
        <div class="role-bar">
          <span class="role-label">当前操作身份：</span>
          <el-radio-group v-model="actorId" size="small" @change="saveActor">
            <el-radio-button :value="h.from_lawyer">交出人（{{ h.from_lawyer_name }}）</el-radio-button>
            <el-radio-button :value="h.to_lawyer">接收人（{{ h.to_lawyer_name }}）</el-radio-button>
          </el-radio-group>
        </div>
      </el-card>

        <!-- 状态引导条 -->
        <el-alert
          v-if="h.status === 'returned'"
          :title="isGiver ? '清单已被退回，请查看退回原因，补入待办或调整后重新提交核对' : '已退回交出人补充，等待其重新提交'"
          :description="h.returned_reason"
          type="error" show-icon :closable="false" style="margin-bottom: 12px"
        />
        <el-alert
          v-else-if="h.status === 'draft' && isGiver"
          title="清单已生成，请确认每项待办的去向，然后提交给接收人核对"
          type="info" show-icon :closable="false" style="margin-bottom: 12px"
        />
        <el-alert
          v-else-if="h.status === 'completed'"
          title="交接已完成，本案由接收人接管；历史办案记录仍保留原承办人，全部操作可在下方留痕中追溯"
          type="success" show-icon :closable="false" style="margin-bottom: 12px"
        />
        <el-alert
          v-else-if="h.status === 'canceled'"
          title="本次交接已取消，承办关系未变更"
          type="info" show-icon :closable="false" style="margin-bottom: 12px"
        />

      <!-- 过期清单拦截提示 -->
      <el-alert
        v-if="stale && h.status === 'pending' && isReceiver"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="交接期间案件待办有新增或变更，不能使用过期清单完成交接"
        description="请点击下方「补入最新待办」，变更项会加入清单并要求重新核对后，方可确认接管。"
      />

      <!-- 待办清单 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div class="card-head">
            <b>交接清单</b>
            <span class="card-sub">
              共 {{ activeItems.length }} 项，已核对 {{ h.checked_count }} 项
              <el-tag v-if="stale" type="danger" size="small" style="margin-left: 8px">有变化</el-tag>
            </span>
            <div>
              <el-button size="small" :loading="refreshing" @click="doRefresh"
                :disabled="!involved || !active">
                补入最新待办
              </el-button>
              <el-button v-if="isGiver && active" size="small" type="primary" plain @click="customDialog = true">
                补充事项
              </el-button>
            </div>
          </div>
        </template>

        <el-table :data="groupedItems" size="small" :row-class-name="rowClass" :span-method="groupSpan" border>
          <el-table-column label="类别" width="110">
            <template #default="{ row }">
              <span v-if="row.groupIndex === 0" class="group-label">{{ row.typeLabel }}</span>
            </template>
          </el-table-column>
          <el-table-column label="事项" min-width="220">
            <template #default="{ row }">
              <span :class="{ removed: row.change_flag === 'removed' }">{{ row.title }}</span>
              <el-tag v-if="row.change_flag === 'new'" type="success" size="small" style="margin-left: 6px">新增</el-tag>
              <el-tag v-else-if="row.change_flag === 'changed'" type="warning" size="small" style="margin-left: 6px">已变更</el-tag>
              <el-tag v-else-if="row.change_flag === 'removed'" type="info" size="small" style="margin-left: 6px">已办结/删除</el-tag>
              <div class="sub">{{ row.detail }}</div>
            </template>
          </el-table-column>
          <el-table-column label="期限/时间" width="120">
            <template #default="{ row }">
              <span v-if="row.hearing_time">{{ row.hearing_time.replace('T', ' ').slice(0, 16) }}</span>
              <span v-else-if="row.due_date">
                {{ row.due_date }}
                <el-tag v-if="row.is_overdue" type="danger" size="small" effect="dark">逾期</el-tag>
              </span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="去向" width="150">
            <template #default="{ row }">
              <el-select
                :model-value="row.destination"
                size="small"
                :disabled="!involved || !active"
                @change="(v) => setDestination(row, v)"
              >
                <el-option label="接收人接管" value="takeover" />
                <el-option label="原责任人继续办理" value="keep" />
                <el-option label="无需办理" value="void" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="接收人核对" width="220">
            <template #default="{ row }">
              <template v-if="row.change_flag !== 'removed'">
                <el-checkbox
                  :model-value="row.checked"
                  :disabled="!isReceiver || !active || h.status === 'draft'"
                  @change="(v) => checkItem(row, v)"
                >已核对</el-checkbox>
                <el-input
                  v-model="row.check_note"
                  size="small"
                  placeholder="核对备注"
                  style="width: 110px; margin-left: 6px"
                  :disabled="!isReceiver || !active"
                  @change="() => checkItem(row, true)"
                />
              </template>
              <span v-else class="sub">不纳入交接</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isGiver && active" label="操作" width="70">
            <template #default="{ row }">
              <el-popconfirm
                v-if="row.item_type === 'custom'"
                title="删除该补充事项？"
                @confirm="deleteCustom(row)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 操作栏 -->
      <el-card v-if="active" shadow="never" style="margin-bottom: 16px">
        <div class="actions">
          <!-- 交出人 -->
          <template v-if="isGiver">
            <el-button
              v-if="h.status === 'draft' || h.status === 'returned'"
              type="primary" :loading="acting" @click="doSubmit">
              {{ h.status === 'returned' ? '补充后重新提交核对' : '提交给接收人核对' }}
            </el-button>
            <el-button v-if="h.status === 'pending'" disabled>等待接收人核对…</el-button>
          </template>
          <!-- 接收人 -->
          <template v-if="isReceiver">
            <template v-if="h.status === 'pending'">
              <el-button type="success" :loading="acting" @click="doConfirm">
                核对无误，确认接管
              </el-button>
              <el-button type="warning" plain @click="returnDialog = true">退回补充</el-button>
            </template>
            <el-button v-else-if="h.status === 'draft'" disabled>等待交出人提交清单</el-button>
            <el-button v-else disabled>清单已退回，等待交出人补充重新提交</el-button>
          </template>
          <!-- 双方均可取消 -->
          <el-button v-if="involved" type="danger" plain @click="cancelDialog = true">取消交接</el-button>
        </div>
        <div v-if="!involved" class="sub">当前操作身份不是本次交接的交出人或接收人，仅可查看。</div>
      </el-card>

      <!-- 操作记录 -->
      <el-card v-if="h.logs?.length" shadow="never">
        <template #header><b>操作留痕</b>
          <span class="card-sub">（完成前后原责任人均可在此追溯）</span>
        </template>
        <el-timeline style="padding-left: 4px; margin-top: 8px">
          <el-timeline-item
            v-for="log in [...h.logs].reverse()"
            :key="log.id"
            :timestamp="`${fmt(log.created_at)} · ${log.actor_name}`"
            placement="top"
            :type="log.action === 'confirm' ? 'success' : log.action === 'cancel' ? 'danger' : log.action === 'return' ? 'warning' : 'primary'"
          >
            {{ log.action_display }}<span v-if="log.note" class="sub"> — {{ log.note }}</span>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>

    <!-- 退回对话框 -->
    <el-dialog v-model="returnDialog" title="退回补充" width="480px">
      <el-alert type="warning" :closable="false"
        title="退回后清单回到交出人，可继续补入待办或调整去向，再重新提交核对" style="margin-bottom: 12px" />
      <el-input v-model="returnReason" type="textarea" :rows="3" placeholder="请说明需要补充/更正的内容（必填）" />
      <template #footer>
        <el-button @click="returnDialog = false">取消</el-button>
        <el-button type="warning" plain :loading="acting" @click="doReturn">确认退回</el-button>
      </template>
    </el-dialog>

    <!-- 取消对话框 -->
    <el-dialog v-model="cancelDialog" title="取消交接" width="480px">
      <el-alert type="info" :closable="false"
        title="取消后承办关系不变，原责任人继续负责本案" style="margin-bottom: 12px" />
      <el-input v-model="cancelReason" type="textarea" :rows="3" placeholder="取消原因（可选）" />
      <template #footer>
        <el-button @click="cancelDialog = false">再想想</el-button>
        <el-button type="danger" plain :loading="acting" @click="doCancel">确认取消</el-button>
      </template>
    </el-dialog>

    <!-- 补充事项 -->
    <el-dialog v-model="customDialog" title="补充交接事项" width="520px">
      <el-form label-width="90px">
        <el-form-item label="事项" required>
          <el-input v-model="customForm.title" placeholder="如：卷宗原件2册、当事人沟通记录U盘" />
        </el-form-item>
        <el-form-item label="详情">
          <el-input v-model="customForm.detail" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="期限">
          <el-date-picker v-model="customForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="去向">
          <el-select v-model="customForm.destination" style="width: 100%">
            <el-option label="接收人接管" value="takeover" />
            <el-option label="原责任人继续办理" value="keep" />
            <el-option label="无需办理" value="void" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="customDialog = false">取消</el-button>
        <el-button type="primary" @click="addCustom">加入清单</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'

const route = useRoute()
const router = useRouter()
const h = ref({})
const loading = ref(false)
const acting = ref(false)
const refreshing = ref(false)
const actorId = ref(Number(localStorage.getItem('handover_actor')) || null)

const returnDialog = ref(false)
const cancelDialog = ref(false)
const customDialog = ref(false)
const returnReason = ref('')
const cancelReason = ref('')
const customForm = reactive({ title: '', detail: '', due_date: null, destination: 'takeover' })

const TYPE_LABELS = { deadline: '未办期限', hearing: '后续开庭', material: '待提交材料', custom: '其他事项' }
const TYPE_ORDER = ['deadline', 'hearing', 'material', 'custom']

const active = computed(() => ['draft', 'pending', 'returned'].includes(h.value.status))
const involved = computed(() => actorId.value && [h.value.from_lawyer, h.value.to_lawyer].includes(actorId.value))
const isGiver = computed(() => actorId.value === h.value.from_lawyer)
const isReceiver = computed(() => actorId.value === h.value.to_lawyer)
const stale = computed(() => !!h.value.stale)
const activeItems = computed(() => (h.value.items || []).filter((i) => i.change_flag !== 'removed'))

const groupedItems = computed(() => {
  const rows = []
  for (const t of TYPE_ORDER) {
    const group = (h.value.items || []).filter((i) => i.item_type === t)
    group.forEach((item, idx) => rows.push({ ...item, typeLabel: TYPE_LABELS[t], groupIndex: idx }))
  }
  return rows
})

function groupSpan({ row, columnIndex }) {
  if (columnIndex !== 0) return { rowspan: 1, colspan: 1 }
  if (row.groupIndex !== 0) return { rowspan: 0, colspan: 0 }
  const size = (h.value.items || []).filter((i) => i.item_type === row.item_type).length
  return { rowspan: size, colspan: 1 }
}

const statusType = (s) => ({
  draft: 'info', pending: 'warning', returned: 'danger',
  completed: 'success', canceled: 'info',
}[s])
const fmt = (t) => (t ? t.replace('T', ' ').slice(0, 16) : '-')
const rowClass = ({ row }) => (row.change_flag === 'removed' ? 'removed-row' : '')

function saveActor(v) {
  localStorage.setItem('handover_actor', String(v))
}

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/handovers/${route.params.id}/`)
    h.value = res.data
    if (!actorId.value) {
      actorId.value = h.value.from_lawyer
      saveActor(actorId.value)
    }
  } finally {
    loading.value = false
  }
}

function post(action, payload) {
  return api.post(`/handovers/${h.value.id}/${action}/`, { actor_lawyer: actorId.value, ...payload })
}

async function doRefresh() {
  refreshing.value = true
  try {
    const res = await post('refresh')
    if (res.data.detail === '清单已是最新') ElMessage.success('清单已是最新，无变化')
    else ElMessage.warning(`清单已更新：${res.data.detail}`)
    h.value = res.data.handover
  } finally {
    refreshing.value = false
  }
}

async function doSubmit() {
  acting.value = true
  try {
    const res = await post('submit')
    h.value = res.data
    ElMessage.success('已提交接收人核对')
  } finally {
    acting.value = false
  }
}

async function checkItem(row, checked) {
  try {
    await api.post(`/handovers/${h.value.id}/items/${row.id}/check/`, {
      actor_lawyer: actorId.value, checked, check_note: row.check_note || '',
    })
    const target = h.value.items.find((i) => i.id === row.id)
    if (target) {
      target.checked = checked
      target.check_note = row.check_note || ''
    }
    h.value.checked_count = activeItems.value.filter((i) => i.checked).length
  } catch (e) {
    load()
  }
}

async function setDestination(row, destination) {
  await api.post(`/handovers/${h.value.id}/items/${row.id}/destination/`, {
    actor_lawyer: actorId.value, destination,
  })
  ElMessage.success('去向已调整，接收人需重新核对该项')
  load()
}

async function doConfirm() {
  // 确认前强制重新拉取，防止页面停留期间案件新增待办、用户用旧数据确认
  const latest = await api.get(`/handovers/${h.value.id}/`)
  h.value = latest.data
  if (stale.value) {
    ElMessage.error('交接期间案件待办有变化，不能使用过期清单完成交接。请先「补入最新待办」并重新核对')
    return
  }
  const unchecked = activeItems.value.filter((i) => !i.checked)
  if (unchecked.length) {
    ElMessage.error(`还有 ${unchecked.length} 项未核对：${unchecked.slice(0, 3).map((i) => i.title).join('、')}`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认已核对全部 ${activeItems.value.length} 项待办并接管本案？交接完成后工作台将按你归集本案。`,
      '确认接管', { type: 'warning', confirmButtonText: '确认接管', cancelButtonText: '再看看' })
  } catch (e) { return }
  acting.value = true
  try {
    const res = await post('confirm')
    h.value = res.data
    ElMessage.success('交接完成，本案已由接收人接管')
  } finally {
    acting.value = false
  }
}

async function doReturn() {
  if (!returnReason.value.trim()) {
    ElMessage.warning('请填写退回原因/补充要求')
    return
  }
  acting.value = true
  try {
    const res = await post('return', { reason: returnReason.value })
    h.value = res.data
    returnDialog.value = false
    returnReason.value = ''
    ElMessage.success('已退回交出人补充')
  } finally {
    acting.value = false
  }
}

async function doCancel() {
  acting.value = true
  try {
    const res = await post('cancel', { reason: cancelReason.value })
    h.value = res.data
    cancelDialog.value = false
    cancelReason.value = ''
    ElMessage.success('交接已取消，承办关系不变')
  } finally {
    acting.value = false
  }
}

async function addCustom() {
  if (!customForm.title.trim()) {
    ElMessage.warning('请填写事项')
    return
  }
  await api.post(`/handovers/${h.value.id}/custom-items`, {
    actor_lawyer: actorId.value, ...customForm,
  })
  ElMessage.success('已加入清单')
  customDialog.value = false
  Object.assign(customForm, { title: '', detail: '', due_date: null, destination: 'takeover' })
  load()
}

async function deleteCustom(row) {
  await api.delete(`/handovers/${h.value.id}/custom-items/${row.id}`, {
    data: { actor_lawyer: actorId.value },
  })
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; }
.title-row { display: flex; align-items: center; gap: 8px; }
.title { font-size: 18px; font-weight: 600; color: #409eff; text-decoration: none; }
.sub { color: #999; font-size: 12px; margin-top: 2px; }
.actor { color: #409eff; }
.role-bar { margin-top: 12px; text-align: right; }
.role-label { color: #666; font-size: 13px; margin-right: 8px; }
.card-head { display: flex; align-items: center; gap: 10px; }
.card-sub { color: #999; font-size: 12px; font-weight: normal; }
.card-head > div { margin-left: auto; }
.actions { display: flex; gap: 10px; align-items: center; }
.group-label { font-weight: 600; color: #303133; }
.removed { color: #bbb; text-decoration: line-through; }
:deep(.removed-row) { background: #fafafa !important; color: #aaa; }
</style>
