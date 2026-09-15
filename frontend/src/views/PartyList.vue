<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline @submit.prevent>
        <el-form-item label="搜索">
          <el-input
            v-model="filters.search"
            placeholder="姓名/名称/证件号/旧名"
            clearable
            style="width: 240px"
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
          <el-button type="warning" @click="openDuplicates">
            重复档案核实
            <el-badge v-if="duplicateCount" :value="duplicateCount" :max="99" type="danger" />
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="parties" v-loading="loading" stripe>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.is_merged" type="info" size="small">已合并旧档</el-tag>
            <el-tag v-else type="success" size="small">有效主档</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="姓名/名称" min-width="210">
          <template #default="{ row }">
            <div>{{ row.name }}</div>
            <div v-if="row.alias_names && row.alias_names.length" class="sub-text">
              旧名：{{ row.alias_names.join('、') }}
            </div>
            <div v-if="row.is_merged" class="sub-text">
              已并入：{{ row.merged_into_name }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="party_type_display" label="类型" width="110" />
        <el-table-column prop="id_number" label="证件号/信用代码" min-width="190">
          <template #default="{ row }">{{ row.id_number || '-' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="140">
          <template #default="{ row }">{{ row.phone || '-' }}</template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.address || '-' }}</template>
        </el-table-column>
        <el-table-column prop="source_system" label="原档来源" width="120" />
        <el-table-column prop="case_count" label="涉案" width="70" align="center" />
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!row.is_merged" link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm
              v-if="!row.is_merged"
              title="确定删除该当事人？案件中的关联记录也会删除"
              @confirm="remove(row)"
            >
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
            <el-button link type="warning" @click="openHistory(row)">
              {{ row.is_merged ? '定位主档' : '合并历史' }}
            </el-button>
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
        <el-form-item label="原档来源">
          <el-input v-model="form.source_system" placeholder="案件登记" />
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

    <!-- 重复档案列表 -->
    <el-dialog v-model="dupVisible" title="待核实重复档案" width="92%" top="4vh">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="系统按证件号、名称和联系方式列出疑似重复档案。证件号不一致的同名档案仅提示核实，不能自动合并。"
        style="margin-bottom: 12px"
      />
      <el-empty v-if="!dupLoading && !groups.length" description="暂无待核实重复档案" />
      <el-collapse v-else v-model="activeGroups" v-loading="dupLoading">
        <el-collapse-item v-for="g in groups" :key="g.id" :name="g.id">
          <template #title>
            <div class="group-title">
              <el-tag :type="confidenceTag(g.confidence)" size="small">{{ confidenceText(g.confidence) }}</el-tag>
              <span>{{ g.match_reasons.join('；') }}</span>
              <span class="sub-text">{{ g.parties.length }} 个档案</span>
              <el-tag v-if="g.blocked" type="danger" size="small">禁止自动合并</el-tag>
            </div>
          </template>

          <el-alert
            v-if="g.blocked"
            type="error"
            :title="g.block_reason"
            :closable="false"
            show-icon
            style="margin-bottom: 10px"
          />
          <el-table :data="g.parties" size="small" border>
            <el-table-column prop="name" label="姓名/名称" min-width="170" />
            <el-table-column prop="party_type_display" label="类型" width="90" />
            <el-table-column label="证件号" min-width="170">
              <template #default="{ row }">{{ row.id_number || '未填写' }}</template>
            </el-table-column>
            <el-table-column label="电话" width="130">
              <template #default="{ row }">{{ row.phone || '未填写' }}</template>
            </el-table-column>
            <el-table-column label="地址" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.address || '未填写' }}</template>
            </el-table-column>
            <el-table-column prop="source_system" label="来源" width="100" />
            <el-table-column prop="case_count" label="涉案" width="60" align="center" />
          </el-table>

          <div class="issue-grid">
            <el-card v-if="g.conflicts.length" shadow="never" class="issue-card">
              <template #header>冲突/待补全信息（{{ g.conflicts.length }}）</template>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item v-for="c in g.conflicts" :key="c.field" :label="c.label">
                  <el-tag v-if="c.conflict_type === 'incomplete'" size="small" type="warning">待补全</el-tag>
                  <el-tag v-else size="small" type="danger">不一致</el-tag>
                  <span class="value-list">{{ c.values.map(v => v || '（空）').join(' / ') }}</span>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>

            <el-card shadow="never" class="issue-card">
              <template #header>涉案关系核实</template>
              <el-alert
                v-for="w in g.relations.role_warnings"
                :key="w.code"
                :title="w.message"
                type="warning"
                :closable="false"
                show-icon
                style="margin-bottom: 8px"
              />
              <div v-if="g.relations.duplicate_roles.length" class="dup-item">
                <b>同案同地位重复关联：{{ g.relations.duplicate_roles.length }} 组</b>
                <div v-for="d in g.relations.duplicate_roles" :key="d.key" class="sub-text">
                  {{ d.case_title }} / {{ d.role_display }}
                  <el-tag v-if="d.requires_client_choice" size="small" type="danger">客户状态不一致</el-tag>
                </div>
              </div>
              <el-text v-if="!g.relations.role_warnings.length && !g.relations.duplicate_roles.length" type="info">
                无同案关系冲突
              </el-text>
            </el-card>
          </div>

          <div class="group-actions">
            <el-button type="primary" :disabled="g.blocked" @click="openMergeConfirm(g)">
              选择主档并逐项确认
            </el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>

    <!-- 合并确认 -->
    <el-dialog v-model="mergeVisible" title="确认重复档案合并" width="820px" append-to-body>
      <template v-if="work.group">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="合并将把所有涉案关系归并至主档；旧档案不会删除，会保留旧名称、原档来源和完整合并记录。"
          style="margin-bottom: 14px"
        />

        <h4>1. 选择主档</h4>
        <el-radio-group v-model="work.master" class="master-list" @change="fillMasterValues">
          <el-radio v-for="p in work.group.parties" :key="p.id" :value="p.id" class="master-radio">
            <b>{{ p.name }}</b>
            <span class="sub-text">
              {{ p.party_type_display }} / {{ p.id_number || '证件未填' }} / {{ p.phone || '电话未填' }}
            </span>
          </el-radio>
        </el-radio-group>

        <h4>2. 逐项确认冲突信息</h4>
        <el-form label-width="120px" size="small">
          <el-form-item v-for="c in work.group.conflicts" :key="c.field" :label="c.label" required>
            <el-radio-group v-model="work.field_resolutions[c.field]">
              <el-radio v-for="v in c.options" :key="v" :value="c.field === 'party_type' ? v : v">
                {{ c.field === 'party_type' ? partyTypeText(v) : v }}
              </el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <h4>3. 核实涉案关系</h4>
        <el-checkbox-group v-model="work.confirmed_role_cases" class="check-list">
          <el-checkbox v-for="w in work.group.relations.role_warnings" :key="w.code" :value="w.case_id">
            {{ w.message }}
          </el-checkbox>
        </el-checkbox-group>

        <el-table
          v-if="work.group.relations.duplicate_roles.length"
          :data="work.group.relations.duplicate_roles"
          size="small"
          border
          style="margin: 8px 0 12px"
        >
          <el-table-column prop="case_title" label="案件" min-width="220" />
          <el-table-column prop="role_display" label="诉讼地位" width="110" />
          <el-table-column label="涉及档案" min-width="180">
            <template #default="{ row }">
              <span v-for="r in row.rows" :key="r.case_party_id" class="mini-line">
                {{ r.party_name }}（{{ r.is_client ? '客户' : '非客户' }}）
              </span>
            </template>
          </el-table-column>
          <el-table-column label="归并后客户状态" width="170">
            <template #default="{ row }">
              <el-radio-group v-model="work.relation_decisions[row.key].is_client">
                <el-radio :value="true">是客户</el-radio>
                <el-radio :value="false">非客户</el-radio>
              </el-radio-group>
            </template>
          </el-table-column>
        </el-table>

        <h4>4. 经办人</h4>
        <el-input v-model="work.operator" placeholder="请输入经办人姓名" style="max-width: 260px" />
      </template>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" :loading="merging" @click="submitMerge">确认合并</el-button>
      </template>
    </el-dialog>

    <!-- 合并历史 / 定位主档 -->
    <el-dialog v-model="historyVisible" title="主档与合并历史" width="820px" append-to-body>
      <div v-if="history" v-loading="historyLoading">
        <el-alert
          v-if="history.party.is_merged"
          type="info"
          :closable="false"
          show-icon
          :title="`该旧档案已并入主档：${history.master.name}（#${history.master.id}）`"
          style="margin-bottom: 12px"
        />
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="主档名称">{{ history.master.name }}</el-descriptions-item>
          <el-descriptions-item label="证件号">{{ history.master.id_number || '-' }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ history.master.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="原档来源">{{ history.master.source_system || '-' }}</el-descriptions-item>
          <el-descriptions-item label="保留旧名" :span="2">
            <el-tag v-for="a in history.aliases" :key="a.id" size="small" style="margin-right: 6px">
              {{ a.name }}（{{ a.source_system || '案件登记' }}）
            </el-tag>
            <span v-if="!history.aliases.length">-</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">合并记录</el-divider>
        <el-timeline>
          <el-timeline-item v-for="r in history.records" :key="r.id" :timestamp="formatTime(r.created_at)">
            <b>{{ r.source_name }}</b> 并入 <b>{{ r.master_name }}</b>
            <div class="sub-text">原档来源：{{ r.source_system || '案件登记' }}；经办人：{{ r.operator || '未记录' }}</div>
            <div class="sub-text">
              关系归并：移动 {{ relationCount(r, 'moved_relations') }} 条，
              合并同案同地位 {{ relationCount(r, 'merged_duplicates') }} 组，
              保留不同诉讼地位 {{ relationCount(r, 'retained_roles') }} 案
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="!history.records.length" description="暂无合并记录" :image-size="60" />
      </div>
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
const blank = {
  id: null, name: '', party_type: 'person', id_number: '', phone: '',
  address: '', source_system: '案件登记', notes: '',
}
const form = reactive({ ...blank })

const dupVisible = ref(false)
const dupLoading = ref(false)
const groups = ref([])
const activeGroups = ref([])
const duplicateCount = ref(0)

const mergeVisible = ref(false)
const merging = ref(false)
const work = reactive({
  group: null,
  master: null,
  field_resolutions: {},
  confirmed_role_cases: [],
  relation_decisions: {},
  operator: '',
})

const historyVisible = ref(false)
const historyLoading = ref(false)
const history = ref(null)

async function load() {
  loading.value = true
  try {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    params.include_merged = 'true'
    const res = await api.get('/parties/', { params })
    parties.value = res.data
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  Object.assign(form, blank, row ? JSON.parse(JSON.stringify(row)) : {})
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

async function openDuplicates() {
  dupVisible.value = true
  dupLoading.value = true
  try {
    const res = await api.get('/parties/duplicates/')
    groups.value = res.data.results
    duplicateCount.value = res.data.count
    activeGroups.value = groups.value.slice(0, 3).map((g) => g.id)
  } finally {
    dupLoading.value = false
  }
}

function confidenceText(value) {
  return { high: '高可信：同证件号', medium: '中可信：同名同联系方式', low: '待核实：仅同名', blocked: '禁止合并' }[value]
}

function confidenceTag(value) {
  return { high: 'success', medium: 'warning', low: 'info', blocked: 'danger' }[value]
}

function partyTypeText(value) {
  return { person: '自然人', org: '法人/组织' }[value] || value
}

function openMergeConfirm(group) {
  work.group = group
  work.master = group.parties[0].id
  work.field_resolutions = {}
  work.confirmed_role_cases = []
  work.relation_decisions = {}
  work.operator = ''
  group.conflicts.forEach((c) => {
    const masterValue = group.parties[0][c.field]
    work.field_resolutions[c.field] = masterValue && c.options.includes(masterValue) ? masterValue : c.options[0]
  })
  group.relations.duplicate_roles.forEach((d) => {
    work.relation_decisions[d.key] = {
      is_client: d.requires_client_choice ? null : d.is_client_options[0],
    }
  })
  mergeVisible.value = true
}

function fillMasterValues(masterId) {
  if (!work.group) return
  const master = work.group.parties.find((p) => p.id === masterId)
  work.group.conflicts.forEach((c) => {
    const current = work.field_resolutions[c.field]
    if (!current || !work.group.parties.some((p) => p[c.field] === current && p.id !== master.id)) {
      work.field_resolutions[c.field] = master[c.field] && c.options.includes(master[c.field])
        ? master[c.field]
        : c.options[0]
    }
  })
}

async function submitMerge() {
  if (!work.master) {
    ElMessage.warning('请选择主档')
    return
  }
  if (work.group.conflicts.some((c) => !work.field_resolutions[c.field])) {
    ElMessage.warning('请逐项确认冲突信息')
    return
  }
  if (work.group.relations.role_warnings.length &&
      work.confirmed_role_cases.length !== work.group.relations.role_warnings.length) {
    ElMessage.warning('请逐项核实并勾选同一案件中的不同诉讼地位')
    return
  }
  if (Object.values(work.relation_decisions).some((v) => typeof v.is_client !== 'boolean')) {
    ElMessage.warning('请确认同案同诉讼地位重复关系的客户状态')
    return
  }
  if (!work.operator.trim()) {
    ElMessage.warning('请填写经办人')
    return
  }

  const sourceParties = work.group.parties.filter((p) => p.id !== work.master).map((p) => p.id)
  merging.value = true
  try {
    await api.post('/parties/merge/', {
      master_party: work.master,
      source_parties: sourceParties,
      field_resolutions: { ...work.field_resolutions },
      confirmed_role_cases: [...work.confirmed_role_cases],
      relation_decisions: work.relation_decisions,
      operator: work.operator.trim(),
    })
    ElMessage.success('合并完成，旧档及历史已保留')
    mergeVisible.value = false
    dupVisible.value = false
    await openDuplicates()
    load()
  } finally {
    merging.value = false
  }
}

async function openHistory(row) {
  historyVisible.value = true
  historyLoading.value = true
  history.value = null
  try {
    const res = await api.get(`/parties/${row.id}/merge-history/`)
    history.value = res.data
  } finally {
    historyLoading.value = false
  }
}

function relationCount(record, key) {
  return record.relation_resolutions?.[key]?.length || 0
}

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : ''
}

onMounted(load)
</script>

<style scoped>
.sub-text {
  color: #86909c;
  font-size: 12px;
  line-height: 1.6;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding-right: 16px;
}
.issue-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.issue-card :deep(.el-card__header) {
  padding: 8px 12px;
  font-weight: 600;
}
.value-list {
  margin-left: 8px;
}
.group-actions {
  margin-top: 12px;
  text-align: right;
}
.master-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}
.master-radio {
  display: flex;
  align-items: flex-start;
  height: auto;
  white-space: normal;
}
.check-list {
  display: flex;
  flex-direction: column;
  margin-bottom: 10px;
}
.dup-item .mini-line {
  display: block;
}
h4 {
  margin: 14px 0 8px;
}
</style>
