<template>
  <div v-loading="loading">
    <!-- 视角切换 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <div class="scope-bar">
        <div>
          <span class="scope-label">工作台视角：</span>
          <el-select v-model="scopeLawyer" clearable placeholder="全所汇总" style="width: 200px" @change="load">
            <el-option v-for="l in lawyers" :key="l.id"
              :label="`${l.name}（${l.title_display}）`" :value="l.id" />
          </el-select>
          <el-tag v-if="data.scope_lawyer_name" type="primary" effect="plain" style="margin-left: 10px">
            {{ data.scope_lawyer_name }} 的个人工作台（交接完成后按新负责人归集）
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- 待我核对的交接 -->
    <el-card v-if="data.handovers_to_review?.length" shadow="never" style="margin-bottom: 16px">
      <template #header><b style="color: #e6a23c">待我核对的案件交接（{{ data.handovers_to_review.length }}）</b></template>
      <div v-for="hv in data.handovers_to_review" :key="hv.id" class="ho-row">
        <div>
          <router-link :to="`/handovers/${hv.id}`" class="link">
            {{ hv.case_title }}
          </router-link>
          <span class="sub-text">{{ hv.case_number }} · {{ hv.from_lawyer_name }} 交接给 {{ hv.to_lawyer_name }}</span>
          <el-tag :type="hv.status === 'returned' ? 'danger' : 'warning'" size="small" style="margin-left: 8px">
            {{ hv.status_display }}
          </el-tag>
          <el-tag v-if="hv.stale" type="danger" size="small" effect="dark" style="margin-left: 4px">清单有变化</el-tag>
        </div>
        <el-button type="primary" size="small" @click="$router.push(`/handovers/${hv.id}`)">去核对</el-button>
      </div>
    </el-card>

    <!-- 我发起、进行中的交接 -->
    <el-card v-if="data.handovers_outgoing?.length" shadow="never" style="margin-bottom: 16px">
      <template #header><b>我发起、进行中的交接（{{ data.handovers_outgoing.length }}）</b>
        <span class="card-sub">完成前你仍是原责任人，待办仍需跟进</span>
      </template>
      <div v-for="hv in data.handovers_outgoing" :key="hv.id" class="ho-row">
        <div>
          <router-link :to="`/handovers/${hv.id}`" class="link">{{ hv.case_title }}</router-link>
          <span class="sub-text">{{ hv.case_number }} · 交给 {{ hv.to_lawyer_name }}</span>
          <el-tag :type="hv.status === 'returned' ? 'danger' : 'info'" size="small" style="margin-left: 8px">
            {{ hv.status_display }}
          </el-tag>
        </div>
        <el-button size="small" @click="$router.push(`/handovers/${hv.id}`)">查看</el-button>
      </div>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-num">{{ data.case_active }}</div>
          <div class="stat-label">在办案件</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-num">{{ data.case_total }}</div>
          <div class="stat-label">案件总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-num">{{ data.party_total }}</div>
          <div class="stat-label">当事人</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card" :class="{ warn: data.deadline_overdue > 0 }">
          <div class="stat-num" :style="data.deadline_overdue > 0 ? 'color:#f56c6c' : ''">
            {{ data.deadline_overdue }}
          </div>
          <div class="stat-label">逾期未办期限</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <!-- 期限提醒 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <b>期限提醒</b>
            <span class="card-sub">（未来30天及已逾期）</span>
          </template>
          <el-table :data="data.deadlines_upcoming" size="small" max-height="420">
            <el-table-column label="事项" min-width="180">
              <template #default="{ row }">
                <router-link :to="`/cases/${row.case}`" class="link">
                  {{ row.title }}
                </router-link>
                <div class="sub-text">{{ row.case_title }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="deadline_type_display" label="类型" width="110" />
            <el-table-column prop="due_date" label="截止日期" width="110" />
            <el-table-column label="剩余" width="90">
              <template #default="{ row }">
                <el-tag :type="daysType(row.days_left)" size="small" effect="dark">
                  {{ daysText(row.days_left) }}
                </el-tag>
              </template>
            </el-table-column>
            <template #empty>近期没有待办期限</template>
          </el-table>
        </el-card>
      </el-col>

      <!-- 近期开庭 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><b>近期开庭</b></template>
          <el-timeline v-if="data.hearings_upcoming?.length" style="padding-left: 4px">
            <el-timeline-item
              v-for="h in data.hearings_upcoming"
              :key="h.id"
              :timestamp="h.hearing_time"
              placement="top"
              type="primary"
            >
              <router-link :to="`/cases/${h.case}`" class="link">{{ h.case_title }}</router-link>
              <div class="sub-text">{{ h.location }}<span v-if="h.judge"> · {{ h.judge }}</span></div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="近期没有开庭安排" :image-size="60" />
        </el-card>

        <!-- 阶段分布 -->
        <el-card shadow="never" style="margin-top: 16px">
          <template #header><b>案件阶段分布</b></template>
          <div v-for="s in data.stage_stats" :key="s.stage" class="stage-row">
            <span class="stage-name">{{ s.stage_display }}</span>
            <el-progress
              :percentage="data.case_total ? Math.round((s.count / data.case_total) * 100) : 0"
              :stroke-width="14"
              style="flex: 1"
            >
              <span class="stage-count">{{ s.count }}</span>
            </el-progress>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'

const loading = ref(false)
const data = ref({ stage_stats: [], deadlines_upcoming: [], hearings_upcoming: [] })
const lawyers = ref([])
const scopeLawyer = ref(
  localStorage.getItem('dashboard_lawyer') ? Number(localStorage.getItem('dashboard_lawyer')) : null)

const daysType = (n) => (n < 0 ? 'danger' : n <= 7 ? 'warning' : 'success')
const daysText = (n) => (n < 0 ? `逾期${-n}天` : n === 0 ? '今天' : `${n}天`)

async function load() {
  loading.value = true
  try {
    localStorage.setItem('dashboard_lawyer', scopeLawyer.value || '')
    const params = {}
    if (scopeLawyer.value) params.lawyer = scopeLawyer.value
    const res = await api.get('/dashboard/', { params })
    data.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  load()
  const res = await api.get('/lawyers/')
  lawyers.value = res.data
})
</script>

<style scoped>
.scope-bar { display: flex; align-items: center; }
.scope-label { color: #666; font-size: 13px; margin-right: 8px; }
.ho-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; border-bottom: 1px dashed #eee;
}
.ho-row:last-child { border-bottom: none; }
.stat-card { text-align: center; }
.stat-num { font-size: 32px; font-weight: 700; color: #1f2d3d; }
.stat-label { color: #888; margin-top: 4px; }
.stat-card.warn { border-color: #f56c6c; }
.card-sub { color: #999; font-size: 12px; font-weight: normal; }
.link { color: #409eff; text-decoration: none; }
.sub-text { color: #999; font-size: 12px; margin-top: 2px; }
.stage-row { display: flex; align-items: center; margin-bottom: 10px; }
.stage-name { width: 48px; color: #666; font-size: 13px; }
.stage-count { font-size: 12px; color: #333; }
</style>
