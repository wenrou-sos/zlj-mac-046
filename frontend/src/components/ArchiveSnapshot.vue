<template>
  <div v-if="snapshot" class="archive-snapshot">
    <el-descriptions :column="3" border size="small">
      <el-descriptions-item label="案号">{{ snapshot.case.case_number }}</el-descriptions-item>
      <el-descriptions-item label="案件名称" :span="2">{{ snapshot.case.title }}</el-descriptions-item>
      <el-descriptions-item label="案件类型">{{ snapshot.case.case_type }}</el-descriptions-item>
      <el-descriptions-item label="结案日期">{{ snapshot.case.closed_date || '-' }}</el-descriptions-item>
      <el-descriptions-item label="封存时间">{{ snapshot.generated_at }}</el-descriptions-item>
      <el-descriptions-item label="案由">{{ snapshot.case.cause || '-' }}</el-descriptions-item>
      <el-descriptions-item label="法院/机构">{{ snapshot.case.court || '-' }}</el-descriptions-item>
      <el-descriptions-item label="标的额(元)">{{ snapshot.case.amount || '-' }}</el-descriptions-item>
      <el-descriptions-item label="立案日期">{{ snapshot.case.filed_date || '-' }}</el-descriptions-item>
      <el-descriptions-item label="整理人">{{ snapshot.prepared_by || '-' }}</el-descriptions-item>
      <el-descriptions-item label="复核人">{{ snapshot.reviewer || '-' }}</el-descriptions-item>
      <el-descriptions-item label="结案摘要" :span="3">{{ snapshot.case.summary || '-' }}</el-descriptions-item>
    </el-descriptions>

    <div class="snap-section">
      <h4>当事人（{{ snapshot.parties.length }}）</h4>
      <el-table :data="snapshot.parties" size="small" border>
        <el-table-column prop="name" label="姓名/名称" min-width="200" />
        <el-table-column prop="role" label="诉讼地位" width="100" />
        <el-table-column prop="id_number" label="证件号" min-width="160" />
        <el-table-column prop="phone" label="电话" width="130" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>承办律师（{{ snapshot.lawyers.length }}）</h4>
      <el-table :data="snapshot.lawyers" size="small" border>
        <el-table-column prop="name" label="姓名" width="90" />
        <el-table-column prop="role" label="角色" width="100" />
        <el-table-column prop="title" label="职称" width="100" />
        <el-table-column prop="bar_number" label="执业证号" min-width="160" />
        <el-table-column prop="phone" label="电话" width="130" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>诉讼阶段（{{ snapshot.stages.length }}）</h4>
      <el-table :data="snapshot.stages" size="small" border>
        <el-table-column prop="log_date" label="日期" width="110" />
        <el-table-column prop="stage" label="阶段" width="100" />
        <el-table-column prop="notes" label="备注" min-width="220" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>庭期安排（{{ snapshot.hearings.length }}）</h4>
      <el-table :data="snapshot.hearings" size="small" border>
        <el-table-column prop="hearing_time" label="开庭时间" width="150" />
        <el-table-column prop="location" label="地点" min-width="200" />
        <el-table-column prop="judge" label="法官/仲裁员" width="120" />
        <el-table-column prop="notes" label="备注" min-width="160" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>案件材料（{{ snapshot.materials.length }}）</h4>
      <el-table :data="snapshot.materials" size="small" border>
        <el-table-column prop="name" label="材料名称" min-width="200" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="submitted_to" label="提交对象" min-width="160" />
        <el-table-column prop="submit_date" label="提交日期" width="110" />
        <el-table-column prop="notes" label="备注" min-width="150" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>期限（{{ snapshot.deadlines.length }}）</h4>
      <el-table :data="snapshot.deadlines" size="small" border>
        <el-table-column prop="due_date" label="截止日期" width="110" />
        <el-table-column prop="title" label="事项" min-width="180" />
        <el-table-column prop="deadline_type" label="类型" width="120" />
        <el-table-column label="办结" width="70">
          <template #default="{ row }">{{ row.is_done ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="notes" label="备注" min-width="160" />
      </el-table>
    </div>

    <div class="snap-section">
      <h4>未结事项处置（{{ snapshot.pending_items.length }}）</h4>
      <el-table :data="snapshot.pending_items" size="small" border>
        <el-table-column prop="kind" label="类别" width="110" />
        <el-table-column prop="title" label="事项" min-width="180" />
        <el-table-column prop="disposition" label="处置方式" width="130" />
        <el-table-column prop="disposition_note" label="处置说明" min-width="220" />
      </el-table>
      <el-empty v-if="!snapshot.pending_items.length" description="无未结事项"
        :image-size="50" />
    </div>
  </div>
  <el-skeleton v-else :rows="6" animated />
</template>

<script setup>
defineProps({
  snapshot: { type: Object, default: null },
})
</script>

<style scoped>
.archive-snapshot { background: #fafbfc; padding: 12px; border: 1px solid #ebeef5; border-radius: 4px; }
.snap-section { margin-top: 14px; }
.snap-section h4 { margin: 0 0 6px; font-size: 14px; }
</style>
