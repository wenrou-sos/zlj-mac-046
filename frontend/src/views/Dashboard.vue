<template>
  <div v-loading="loading">
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
          <div class="stat-num">{{ data.sealed_total || 0 }}</div>
          <div class="stat-label">已封存卷宗</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card"
          :class="{ warn: (data.pending_review_total || 0) > 0 }">
          <div class="stat-num" :style="(data.pending_review_total || 0) > 0 ? 'color:#e6a23c' : ''">
            {{ data.pending_review_total || 0 }}
          </div>
          <div class="stat-label">待复核卷宗</div>
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
      <!-- 待复核卷宗 -->
      <el-col :span="24" v-if="data.pending_review?.length">
        <el-card shadow="never" style="margin-bottom: 16px">
          <template #header>
            <b>待复核卷宗</b>
            <span class="card-sub">（等待复核人确认封存）</span>
          </template>
          <el-table :data="data.pending_review" size="small">
            <el-table-column prop="case_number" label="案号" width="220" />
            <el-table-column label="案件名称" min-width="220">
              <template #default="{ row }">
                <router-link :to="`/cases/${row.case_id}?tab=archive`" class="link">{{ row.case_title }}</router-link>
              </template>
            </el-table-column>
            <el-table-column label="版本" width="80">
              <template #default="{ row }">v{{ row.version_no }}</template>
            </el-table-column>
            <el-table-column prop="pending_count" label="未结事项" width="90" align="center" />
            <el-table-column prop="submitted_by" label="提交人" width="100" />
            <el-table-column prop="submitted_at" label="提交时间" width="150" />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <router-link :to="`/cases/${row.case_id}?tab=archive`" class="link">前往复核</router-link>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 0">
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

const daysType = (n) => (n < 0 ? 'danger' : n <= 7 ? 'warning' : 'success')
const daysText = (n) => (n < 0 ? `逾期${-n}天` : n === 0 ? '今天' : `${n}天`)

onMounted(async () => {
  loading.value = true
  try {
    const res = await api.get('/dashboard/')
    data.value = res.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
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
