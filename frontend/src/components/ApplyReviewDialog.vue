<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="发起利益冲突复核申请"
    width="640px"
    @open="onOpen"
  >
    <el-alert
      type="info"
      :closable="false"
      title="提交后系统将冻结当事人身份、拟承接涉案关系与风险依据快照，由指定复核人独立审批；申请人不能审批自己的申请。"
      style="margin-bottom: 14px"
    />
    <el-form label-width="104px">
      <el-form-item label="目标案件" required>
        <el-select v-model="form.case_id" filterable placeholder="选择案件" style="width: 100%">
          <el-option v-for="c in cases" :key="c.id"
            :label="`${c.case_number} ${c.title}`" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="拟承接当事人" required>
        <el-select
          v-model="form.party_id"
          filterable remote :remote-method="searchParties"
          :loading="partyLoading" placeholder="输入姓名/名称检索"
          style="width: 100%"
        >
          <el-option v-for="p in partyOptions" :key="p.id" :label="p.name" :value="p.id">
            <span>{{ p.name }}</span>
            <span class="opt-sub">{{ p.party_type_display }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="拟列诉讼地位">
        <el-select v-model="form.proposed_role" style="width: 100%">
          <el-option v-for="(label, key) in roleMap" :key="key" :label="label" :value="key" />
        </el-select>
      </el-form-item>
      <el-form-item label="是否本所客户">
        <el-switch v-model="form.proposed_is_client" active-text="是（接受委托）" inactive-text="否（对方当事人）" />
      </el-form-item>
      <el-form-item label="指定复核人" required>
        <el-select v-model="form.reviewer" filterable placeholder="选择独立复核人" style="width: 100%">
          <el-option
            v-for="l in reviewers" :key="l.id"
            :label="`${l.name}（${l.title_display}）`" :value="l.id"
            :disabled="l.id === identity.lawyerId"
          />
        </el-select>
        <div v-if="identity.lawyerId" class="form-hint">申请人本人已被排除，不能自审</div>
      </el-form-item>
      <el-form-item label="申请说明">
        <el-input v-model="form.apply_remark" type="textarea" :rows="2" placeholder="委托背景、拟采取的风险隔离措施等" />
      </el-form-item>

      <el-form-item label="随附材料">
        <div style="width: 100%">
          <div v-for="(m, i) in form.materials" :key="i" class="mat-row">
            <el-input v-model="m.name" placeholder="材料名称（如 知情同意书）" style="width: 200px" />
            <el-input v-model="m.source" placeholder="来源/出具方" style="width: 170px" />
            <el-button link type="danger" @click="form.materials.splice(i, 1)">删除</el-button>
          </div>
          <el-button link type="primary" @click="form.materials.push({ name: '', source: '' })">+ 添加材料</el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">提交复核申请</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { identity } from '../identity'

const props = defineProps({
  modelValue: Boolean,
  presetCase: { type: [Number, Object], default: null },
  presetParty: { type: [Number, Object], default: null },
  presetRole: { type: String, default: '' },
  presetIsClient: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'created'])

const roleMap = {
  plaintiff: '原告', defendant: '被告', third: '第三人', appellant: '上诉人',
  appellee: '被上诉人', applicant: '申请执行人', respondent: '被执行人',
  suspect: '犯罪嫌疑人', victim: '被害人',
}

const cases = ref([])
const partyOptions = ref([])
const partyLoading = ref(false)
const reviewers = ref([])
const saving = ref(false)

const form = reactive({
  case_id: null, party_id: null, proposed_role: 'plaintiff',
  proposed_is_client: false, reviewer: null, apply_remark: '',
  materials: [],
})

async function onOpen() {
  if (!identity.lawyerId) {
    ElMessage.warning('请先在右上角选择当前操作律师（申请人）')
    emit('update:modelValue', false)
    return
  }
  form.case_id = typeof props.presetCase === 'object' ? props.presetCase?.id : props.presetCase
  form.party_id = typeof props.presetParty === 'object' ? props.presetParty?.id : props.presetParty
  form.proposed_role = props.presetRole || 'plaintiff'
  form.proposed_is_client = !!props.presetIsClient
  form.reviewer = null
  form.apply_remark = ''
  form.materials = []
  if (!cases.value.length) {
    const [cs, ls] = await Promise.all([
      api.get('/cases/'),
      api.get('/lawyers/'),
    ])
    cases.value = cs.data
    reviewers.value = ls.data
  }
  if (form.party_id) {
    const res = await api.get('/parties/', { params: { search: '' } })
    partyOptions.value = res.data
  } else {
    searchParties('')
  }
}

async function searchParties(kw) {
  partyLoading.value = true
  try {
    const res = await api.get('/parties/', { params: { search: kw || '' } })
    partyOptions.value = res.data
  } finally {
    partyLoading.value = false
  }
}

async function submit() {
  if (!form.case_id || !form.party_id) {
    ElMessage.warning('请选择目标案件和拟承接当事人')
    return
  }
  if (!form.reviewer) {
    ElMessage.warning('请指定复核人')
    return
  }
  if (form.reviewer === identity.lawyerId) {
    ElMessage.error('申请人不能同时担任复核人')
    return
  }
  saving.value = true
  try {
    const payload = {
      case: form.case_id, party: form.party_id,
      proposed_role: form.proposed_role,
      proposed_is_client: form.proposed_is_client,
      reviewer: form.reviewer, apply_remark: form.apply_remark,
      materials: form.materials.filter((m) => m.name),
    }
    const res = await api.post('/conflict-reviews/apply/', payload)
    ElMessage.success(`复核申请已提交（${res.data.review_number}），等待复核人审批`)
    emit('update:modelValue', false)
    emit('created', res.data)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.opt-sub { float: right; color: #999; font-size: 12px; }
.form-hint { color: #909399; font-size: 12px; line-height: 1.4; }
.mat-row { display: flex; gap: 8px; margin-bottom: 8px; }
</style>
