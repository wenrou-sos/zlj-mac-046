<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-alert
        type="info"
        :closable="false"
        title="在接受新委托前，输入当事人姓名/名称或证件号，检查其与本所现有案件是否存在利益冲突"
        style="margin-bottom: 16px"
      />
      <el-form inline @submit.prevent="check">
        <el-form-item label="姓名/名称">
          <el-input v-model="name" placeholder="支持模糊检索，如 周文斌 / 中科" style="width: 240px" />
        </el-form-item>
        <el-form-item label="证件号">
          <el-input v-model="idNumber" placeholder="精确匹配（可选）" style="width: 240px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="check">开始检查</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <template v-if="checked">
      <el-alert
        v-if="!results.length"
        type="success"
        :closable="false"
        title="未检索到该当事人在本所有任何涉诉记录，未发现利益冲突"
        style="margin-bottom: 16px"
      />

      <el-card v-for="r in results" :key="r.party.id" shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div class="result-head">
            <span>
              <b>{{ r.party.name }}</b>
              <span class="meta">{{ r.party.party_type_display }}<template v-if="r.party.id_number"> · {{ r.party.id_number }}</template></span>
            </span>
            <el-tag :type="riskType(r.risk)" effect="dark">{{ riskText(r.risk) }}</el-tag>
          </div>
        </template>

        <el-alert
          v-for="(w, i) in r.warnings"
          :key="i"
          :type="r.risk === 'high' ? 'error' : 'warning'"
          :closable="false"
          :title="w"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-if="!r.warnings.length"
          type="success"
          :closable="false"
          title="该当事人有档案记录，但未发现冲突情形"
          style="margin-bottom: 8px"
        />

        <el-table v-if="r.involvements.length" :data="r.involvements" size="small" style="margin-top: 8px">
          <el-table-column label="案件" min-width="220">
            <template #default="{ row }">
              <router-link :to="`/cases/${row.case_id}`" class="link">{{ row.case_title }}</router-link>
              <div class="sub">{{ row.case_number }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="stage_display" label="阶段" width="90" />
          <el-table-column prop="role_display" label="诉讼地位" width="110" />
          <el-table-column label="本所客户" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_client" type="success" size="small">是</el-tag>
              <span v-else>否</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const name = ref('')
const idNumber = ref('')
const loading = ref(false)
const checked = ref(false)
const results = ref([])

const riskType = (r) => ({ high: 'danger', medium: 'warning', low: 'success' }[r])
const riskText = (r) => ({ high: '高风险：存在利益冲突', medium: '需关注', low: '低风险' }[r])

async function check() {
  if (!name.value && !idNumber.value) {
    ElMessage.warning('请输入姓名/名称或证件号')
    return
  }
  loading.value = true
  try {
    const res = await api.get('/conflict-check/', {
      params: { name: name.value, id_number: idNumber.value },
    })
    results.value = res.data.results
    checked.value = true
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.result-head { display: flex; justify-content: space-between; align-items: center; }
.meta { color: #999; font-size: 12px; margin-left: 10px; font-weight: normal; }
.link { color: #409eff; text-decoration: none; }
.sub { color: #999; font-size: 12px; }
</style>
