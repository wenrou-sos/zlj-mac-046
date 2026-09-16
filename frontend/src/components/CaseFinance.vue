<template>
  <div v-loading="loading">
    <el-alert v-if="!auth.user" type="warning" :closable="false" style="margin-bottom: 12px"
      title="当前为匿名浏览：提交工时/费用、核准、出账与收款需先登录（右上角）" />
    <!-- 汇总：应收/已收/未收，标的额仅作参考、不参与律师费统计 -->
    <div class="fin-summary">
      <div class="stat">
        <div class="stat-label">应收合计</div>
        <div class="stat-value">¥{{ fmt(summary.billed_total) }}</div>
        <div class="stat-sub" v-if="Number(summary.reduction_total) > 0">
          已减免 ¥{{ fmt(summary.reduction_total) }}
        </div>
      </div>
      <div class="stat">
        <div class="stat-label">已收</div>
        <div class="stat-value green">¥{{ fmt(summary.received_total) }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">未收</div>
        <div class="stat-value orange">¥{{ fmt(summary.outstanding_total) }}</div>
      </div>
      <div class="stat">
        <div class="stat-label">待出账（已核准）</div>
        <div class="stat-value">¥{{ fmt(unbilledTotal) }}</div>
        <div class="stat-sub">工时 ¥{{ fmt(summary.unbilled_time_amount) }} /
          费用 ¥{{ fmt(summary.unbilled_expense_amount) }}</div>
      </div>
      <div class="stat muted">
        <div class="stat-label">标的额（非律师费）</div>
        <div class="stat-value">{{ caseAmount ? `¥${fmt(caseAmount)}` : '-' }}</div>
        <div class="stat-sub">与律师费分开核算</div>
      </div>
    </div>

    <!-- 收费约定 -->
    <el-card shadow="never" class="fin-card">
      <template #header>
        <div class="card-head">
          <span>收费约定</span>
          <el-button v-if="canManage" type="primary" size="small" @click="openAgreementDialog">
            {{ agreement ? '修改约定' : '设置收费约定' }}
          </el-button>
        </div>
      </template>
      <template v-if="agreement">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="收费方式">
            <el-tag size="small" :type="agreement.fee_type === 'fixed' ? 'success' : 'primary'">
              {{ agreement.fee_type_display }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="agreement.fee_type === 'fixed'" label="固定收费总额">
            ¥{{ fmt(agreement.fixed_amount) }}
          </el-descriptions-item>
          <el-descriptions-item label="约定说明" :span="2">
            {{ agreement.notes || '-' }}
          </el-descriptions-item>
        </el-descriptions>
        <template v-if="agreement.fee_type === 'hourly'">
          <div class="section-bar">
            <span class="section-title">计时费率</span>
            <el-button v-if="canManage" size="small" @click="openRateDialog">设置/变更费率</el-button>
          </div>
          <el-table :data="rates" size="small">
            <el-table-column prop="lawyer_name" label="律师" width="120" />
            <el-table-column label="小时费率" width="140">
              <template #default="{ row }">¥{{ fmt(row.hourly_rate) }}/小时</template>
            </el-table-column>
            <el-table-column prop="effective_date" label="生效日期" width="120" />
            <el-table-column label="说明">
              <template #default="{ $index }">
                <span class="sub">{{ $index === 0 ? '当前适用' : '历史费率' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-alert type="info" :closable="false" style="margin-top: 8px"
            title="费率变更仅影响生效日之后提交的工时；已出账项目保留当时计价依据。" />
        </template>
      </template>
      <el-empty v-else description="尚未设置收费约定，设置后律师才能提交工时/费用并出账"
        :image-size="60" />
    </el-card>

    <!-- 工时记录 -->
    <el-card shadow="never" class="fin-card">
      <template #header>
        <div class="card-head">
          <span>工时记录</span>
          <el-button v-if="auth.user" type="primary" size="small" @click="openTimeDialog">记工时</el-button>
        </div>
      </template>
      <el-table :data="timeEntries" size="small">
        <el-table-column prop="work_date" label="日期" width="100" />
        <el-table-column prop="lawyer_name" label="律师" width="90" />
        <el-table-column prop="hours" label="工时(h)" width="80" align="right" />
        <el-table-column label="费率" width="110" align="right">
          <template #default="{ row }">
            {{ row.hourly_rate ? `¥${fmt(row.hourly_rate)}` : '不计费' }}
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">
            {{ row.amount ? `¥${fmt(row.amount)}` : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="description" label="工作内容" min-width="180" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="workStatusType(row.status)">
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账单" width="120">
          <template #default="{ row }">
            <el-link v-if="row.bill_number" type="primary" @click="openBillById(row.bill_id)">
              {{ row.bill_number }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button v-if="canManage && row.status === 'pending'" link type="success" size="small"
              @click="approve('/time-entries/', row)">核准</el-button>
            <el-button v-if="canManage && row.status === 'approved'" link type="warning" size="small"
              @click="reject('/time-entries/', row)">退回</el-button>
            <el-popconfirm v-if="canEditEntry(row)" title="确定删除该工时记录？"
              @confirm="delEntry('/time-entries/', row)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!timeEntries.length" description="暂无工时记录" :image-size="60" />
    </el-card>

    <!-- 代垫费用 -->
    <el-card shadow="never" class="fin-card">
      <template #header>
        <div class="card-head">
          <span>代垫费用</span>
          <el-button v-if="auth.user" type="primary" size="small" @click="openExpenseDialog">登记费用</el-button>
        </div>
      </template>
      <el-table :data="expenses" size="small">
        <el-table-column prop="expense_date" label="日期" width="100" />
        <el-table-column prop="lawyer_name" label="代垫人" width="90" />
        <el-table-column prop="category_display" label="类别" width="110" />
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">¥{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="description" label="费用说明" min-width="180" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="workStatusType(row.status)">
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账单" width="120">
          <template #default="{ row }">
            <el-link v-if="row.bill_number" type="primary" @click="openBillById(row.bill_id)">
              {{ row.bill_number }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button v-if="canManage && row.status === 'pending'" link type="success" size="small"
              @click="approve('/expenses/', row)">核准</el-button>
            <el-button v-if="canManage && row.status === 'approved'" link type="warning" size="small"
              @click="reject('/expenses/', row)">退回</el-button>
            <el-popconfirm v-if="canEditEntry(row)" title="确定删除该费用记录？"
              @confirm="delEntry('/expenses/', row)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!expenses.length" description="暂无代垫费用" :image-size="60" />
    </el-card>

    <!-- 分期账单 -->
    <el-card shadow="never" class="fin-card">
      <template #header>
        <div class="card-head">
          <span>分期账单</span>
          <el-button v-if="canManage" type="primary" size="small" @click="openBillDialog">生成账单</el-button>
        </div>
      </template>
      <el-table :data="bills" size="small">
        <el-table-column prop="bill_number" label="账单编号" width="110" />
        <el-table-column prop="title" label="期次/说明" min-width="170" />
        <el-table-column prop="issue_date" label="出账日期" width="100" />
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">¥{{ fmt(row.total_amount) }}</template>
        </el-table-column>
        <el-table-column label="减免" width="100" align="right">
          <template #default="{ row }">
            <span v-if="Number(row.reduction_amount) > 0" class="reduction">
              -¥{{ fmt(row.reduction_amount) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="已收" width="110" align="right">
          <template #default="{ row }">¥{{ fmt(row.received_amount) }}</template>
        </el-table-column>
        <el-table-column label="未收" width="110" align="right">
          <template #default="{ row }">
            <b v-if="row.status !== 'void' && Number(row.outstanding) > 0">
              ¥{{ fmt(row.outstanding) }}
            </b>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="billStatusType(row.status)">
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openBillDetail(row)">
              明细
            </el-button>
            <template v-if="canManage && row.status !== 'void'">
              <el-button v-if="Number(row.outstanding) > 0" link type="success" size="small"
                @click="openPaymentDialog(row)">收款</el-button>
              <el-button link type="warning" size="small"
                @click="openReductionDialog(row)">减免</el-button>
              <el-button link type="danger" size="small" @click="voidBill(row)">冲正</el-button>
              <el-popconfirm v-if="!row.payments.length" title="确定删除该账单？明细中的工时/费用将释放回已核准"
                @confirm="delBill(row)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!bills.length" description="暂无账单" :image-size="60" />
    </el-card>

    <!-- 收费约定对话框 -->
    <el-dialog v-model="agreementDialog" title="收费约定" width="480px">
      <el-form label-width="110px">
        <el-form-item label="收费方式">
          <el-radio-group v-model="agreementForm.fee_type">
            <el-radio value="fixed">固定收费</el-radio>
            <el-radio value="hourly">按工时收费</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="agreementForm.fee_type === 'fixed'" label="收费总额(元)" required>
          <el-input-number v-model="agreementForm.fixed_amount" :min="0" :precision="2"
            :controls="false" style="width: 200px" />
        </el-form-item>
        <el-form-item label="约定说明">
          <el-input v-model="agreementForm.notes" type="textarea" :rows="2"
            placeholder="如 分三期支付，签约/开庭/结案各付三分之一" />
        </el-form-item>
      </el-form>
      <el-alert v-if="agreementForm.fee_type === 'hourly'" type="info" :closable="false"
        title="保存后请在“计时费率”中为承办律师设置小时费率" />
      <template #footer>
        <el-button @click="agreementDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAgreement">保存</el-button>
      </template>
    </el-dialog>

    <!-- 费率对话框 -->
    <el-dialog v-model="rateDialog" title="设置/变更费率" width="440px">
      <el-form label-width="100px">
        <el-form-item label="律师" required>
          <el-select v-model="rateForm.lawyer" style="width: 100%">
            <el-option v-for="l in lawyerOptions" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="小时费率(元)" required>
          <el-input-number v-model="rateForm.hourly_rate" :min="1" :precision="2"
            :controls="false" style="width: 180px" />
        </el-form-item>
        <el-form-item label="生效日期" required>
          <el-date-picker v-model="rateForm.effective_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false"
        title="新费率只影响生效日之后提交的工时，历史记录与已出账项目不受影响" />
      <template #footer>
        <el-button @click="rateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 记工时对话框 -->
    <el-dialog v-model="timeDialog" title="记工时" width="440px">
      <el-form label-width="90px">
        <el-form-item label="律师" required>
          <el-select v-model="timeForm.lawyer" style="width: 100%">
            <el-option v-for="l in lawyerOptions" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="工作日期" required>
          <el-date-picker v-model="timeForm.work_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="工时(小时)" required>
          <el-input-number v-model="timeForm.hours" :min="0.5" :max="24" :step="0.5" />
        </el-form-item>
        <el-form-item label="工作内容" required>
          <el-input v-model="timeForm.description" type="textarea" :rows="2"
            placeholder="如 起草代理词、出庭、会见当事人" />
        </el-form-item>
      </el-form>
      <el-alert v-if="isHourly" type="info" :closable="false"
        title="提交时将按工作日期自动套用当时生效的费率" />
      <el-alert v-else type="info" :closable="false"
        title="本案为固定收费，工时仅记录工作量，不参与出账" />
      <template #footer>
        <el-button @click="timeDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTimeEntry">保存</el-button>
      </template>
    </el-dialog>

    <!-- 代垫费用对话框 -->
    <el-dialog v-model="expenseDialog" title="登记代垫费用" width="440px">
      <el-form label-width="90px">
        <el-form-item label="代垫人" required>
          <el-select v-model="expenseForm.lawyer" style="width: 100%">
            <el-option v-for="l in lawyerOptions" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="费用日期" required>
          <el-date-picker v-model="expenseForm.expense_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="expenseForm.category" style="width: 100%">
            <el-option v-for="(label, key) in expenseCategoryMap" :key="key"
              :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(元)" required>
          <el-input-number v-model="expenseForm.amount" :min="0.01" :precision="2"
            :controls="false" style="width: 180px" />
        </el-form-item>
        <el-form-item label="费用说明" required>
          <el-input v-model="expenseForm.description" placeholder="如 一审案件受理费" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="expenseDialog = false">取消</el-button>
        <el-button type="primary" @click="saveExpense">保存</el-button>
      </template>
    </el-dialog>

    <!-- 生成账单对话框 -->
    <el-dialog v-model="billDialog" title="生成账单" width="720px">
      <el-form label-width="90px" inline>
        <el-form-item label="期次/说明" required>
          <el-input v-model="billForm.title" style="width: 220px" />
        </el-form-item>
        <el-form-item label="出账日期" required>
          <el-date-picker v-model="billForm.issue_date" type="date"
            value-format="YYYY-MM-DD" style="width: 150px" />
        </el-form-item>
        <el-form-item label="付款期限">
          <el-date-picker v-model="billForm.due_date" type="date"
            value-format="YYYY-MM-DD" style="width: 150px" />
        </el-form-item>
      </el-form>

      <template v-if="isHourly">
        <div class="pick-title">已核准工时（勾选纳入本账单）</div>
        <el-table ref="timeTableRef" :data="approvedTimeEntries" size="small" max-height="200"
          @selection-change="(rows) => (billForm.selectedEntries = rows)">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="work_date" label="日期" width="95" />
          <el-table-column prop="lawyer_name" label="律师" width="80" />
          <el-table-column prop="hours" label="工时" width="60" align="right" />
          <el-table-column label="费率" width="100" align="right">
            <template #default="{ row }">¥{{ fmt(row.hourly_rate) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="100" align="right">
            <template #default="{ row }">¥{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="description" label="工作内容" min-width="140" />
        </el-table>
        <el-empty v-if="!approvedTimeEntries.length" description="没有已核准待出账的工时"
          :image-size="50" />
      </template>

      <div class="pick-title">已核准代垫费用（勾选纳入本账单）</div>
      <el-table ref="expenseTableRef" :data="approvedExpenses" size="small" max-height="160"
        @selection-change="(rows) => (billForm.selectedExpenses = rows)">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="expense_date" label="日期" width="95" />
        <el-table-column prop="category_display" label="类别" width="110" />
        <el-table-column label="金额" width="100" align="right">
          <template #default="{ row }">¥{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="description" label="费用说明" min-width="150" />
      </el-table>
      <el-empty v-if="!approvedExpenses.length" description="没有已核准待出账的费用" :image-size="50" />

      <div class="pick-title">
        固定收费期款
        <el-button size="small" link type="primary" @click="addFixedLine">+ 添加一行</el-button>
      </div>
      <el-alert v-if="agreement?.fee_type === 'fixed'" type="info" :closable="false"
        style="margin-bottom: 8px"
        :title="`约定总额 ¥${fmt(agreement.fixed_amount)}，已出账 ¥${fmt(fixedBilled)}，剩余可出 ¥${fmt(fixedRemaining)}`" />
      <div v-for="(line, i) in billForm.fixed_lines" :key="i" class="fixed-line">
        <el-input v-model="line.description" placeholder="如 固定收费第二期（一审开庭）"
          style="flex: 1" />
        <el-input-number v-model="line.amount" :min="0.01" :precision="2" :controls="false"
          placeholder="金额" style="width: 140px" />
        <el-button link type="danger" @click="billForm.fixed_lines.splice(i, 1)">移除</el-button>
      </div>

      <div class="bill-total">
        本账单合计：<b>¥{{ fmt(billTotal) }}</b>
      </div>
      <template #footer>
        <el-button @click="billDialog = false">取消</el-button>
        <el-button type="primary" :disabled="billTotal <= 0" @click="createBill">
          生成账单
        </el-button>
      </template>
    </el-dialog>

    <!-- 账单明细对话框 -->
    <el-dialog v-model="billDetailDialog" :title="`账单明细 ${currentBill?.bill_number || ''}`"
      width="760px">
      <template v-if="currentBill">
        <el-descriptions :column="4" size="small" border>
          <el-descriptions-item label="期次">{{ currentBill.title }}</el-descriptions-item>
          <el-descriptions-item label="出账日期">{{ currentBill.issue_date }}</el-descriptions-item>
          <el-descriptions-item label="付款期限">{{ currentBill.due_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="billStatusType(currentBill.status)">
              {{ currentBill.status_display }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentBill.status === 'void'" label="冲正原因" :span="4">
            {{ currentBill.void_reason }}
          </el-descriptions-item>
          <el-descriptions-item v-if="Number(currentBill.reduction_amount) > 0"
            label="减免" :span="4">
            -¥{{ fmt(currentBill.reduction_amount) }}（{{ currentBill.reduction_reason }}）
          </el-descriptions-item>
        </el-descriptions>

        <div class="pick-title">收费明细（保留出账时计价依据）</div>
        <el-table :data="currentBill.lines" size="small">
          <el-table-column prop="line_type_display" label="类型" width="90" />
          <el-table-column prop="description" label="摘要" min-width="220" />
          <el-table-column label="工时" width="70" align="right">
            <template #default="{ row }">{{ row.quantity || '-' }}</template>
          </el-table-column>
          <el-table-column label="费率/单价" width="110" align="right">
            <template #default="{ row }">
              {{ row.unit_price ? `¥${fmt(row.unit_price)}` : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="金额" width="110" align="right">
            <template #default="{ row }">¥{{ fmt(row.amount) }}</template>
          </el-table-column>
        </el-table>

        <div class="pick-title">收款记录（收款不可删除，录入错误以红冲更正）</div>
        <el-table :data="currentBill.payments" size="small">
          <el-table-column prop="received_date" label="收款日期" width="110" />
          <el-table-column prop="method_display" label="方式" width="100" />
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              <span :class="{ reversal: row.is_reversal }">
                {{ row.is_reversal ? '' : '+' }}¥{{ fmt(row.amount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="notes" label="备注" min-width="160">
            <template #default="{ row }">
              {{ row.notes }}
              <el-tag v-if="row.is_reversal" size="small" type="danger" effect="plain">冲正退款</el-tag>
              <el-tag v-else-if="row.is_reversed" size="small" type="info" effect="plain">已红冲</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{ row }">
              <el-button
                v-if="canManage && currentBill.status !== 'void'
                      && !row.is_reversal && !row.is_reversed"
                link type="danger" size="small"
                @click="reversePayment(row)">红冲</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!currentBill.payments.length" description="暂无收款记录" :image-size="50" />
      </template>
    </el-dialog>

    <!-- 收款对话框 -->
    <el-dialog v-model="paymentDialog" :title="`收款 ${currentBill?.bill_number || ''}`"
      width="440px">
      <el-form label-width="90px">
        <el-form-item label="未收余额">
          <b>¥{{ fmt(currentBill?.outstanding) }}</b>
        </el-form-item>
        <el-form-item label="收款金额" required>
          <el-input-number v-model="paymentForm.amount" :min="0.01" :precision="2"
            :controls="false" style="width: 180px" />
          <el-button link type="primary" style="margin-left: 8px"
            @click="paymentForm.amount = Number(currentBill?.outstanding)">全额</el-button>
        </el-form-item>
        <el-form-item label="收款日期" required>
          <el-date-picker v-model="paymentForm.received_date" type="date"
            value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="收款方式">
          <el-select v-model="paymentForm.method" style="width: 100%">
            <el-option label="银行转账" value="bank" />
            <el-option label="现金" value="cash" />
            <el-option label="支票" value="check" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="paymentForm.notes" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="paymentDialog = false">取消</el-button>
        <el-button type="primary" @click="savePayment">确认收款</el-button>
      </template>
    </el-dialog>

    <!-- 减免对话框 -->
    <el-dialog v-model="reductionDialog" :title="`费用减免 ${currentBill?.bill_number || ''}`"
      width="440px">
      <el-form label-width="90px">
        <el-form-item label="账单金额">
          <b>¥{{ fmt(currentBill?.total_amount) }}</b>
          <span class="sub" style="margin-left: 8px">
            已收 ¥{{ fmt(currentBill?.received_amount) }}
          </span>
        </el-form-item>
        <el-form-item label="减免金额" required>
          <el-input-number v-model="reductionForm.amount" :min="0" :precision="2"
            :controls="false" style="width: 180px" />
        </el-form-item>
        <el-form-item label="减免原因" required>
          <el-input v-model="reductionForm.reason" type="textarea" :rows="2"
            placeholder="如 当事人经济困难，主任批准减免" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reductionDialog = false">取消</el-button>
        <el-button type="primary" @click="saveReduction">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import { auth } from '../auth'

const props = defineProps({
  caseId: { type: [String, Number], required: true },
  caseLawyers: { type: Array, default: () => [] },
  caseAmount: { type: [String, Number], default: null },
})

const expenseCategoryMap = {
  court_fee: '诉讼费/仲裁费', travel: '差旅费', notary: '公证费',
  appraisal: '鉴定费', courier: '快递/文印', other: '其他',
}

const loading = ref(false)
const agreement = ref(null)
const rates = ref([])
const timeEntries = ref([])
const expenses = ref([])
const bills = ref([])
const summary = ref({})

const agreementDialog = ref(false)
const rateDialog = ref(false)
const timeDialog = ref(false)
const expenseDialog = ref(false)
const billDialog = ref(false)
const billDetailDialog = ref(false)
const paymentDialog = ref(false)
const reductionDialog = ref(false)

const currentBill = ref(null)
const timeTableRef = ref(null)
const expenseTableRef = ref(null)

const today = new Date().toISOString().slice(0, 10)
const agreementForm = reactive({ fee_type: 'hourly', fixed_amount: null, notes: '' })
const rateForm = reactive({ lawyer: null, hourly_rate: null, effective_date: today })
const timeForm = reactive({ lawyer: null, work_date: today, hours: 1, description: '' })
const expenseForm = reactive({
  lawyer: null, expense_date: today, category: 'court_fee', amount: null, description: '',
})
const billForm = reactive({
  title: '', issue_date: today, due_date: null,
  selectedEntries: [], selectedExpenses: [], fixed_lines: [],
})
const paymentForm = reactive({ amount: null, received_date: today, method: 'bank', notes: '' })
const reductionForm = reactive({ amount: 0, reason: '' })

const lawyerOptions = computed(() => {
  // 非管理员只能以本人名义提交
  if (auth.user && !auth.user.is_staff && auth.user.lawyer_id) {
    return props.caseLawyers
      .map((cl) => cl.lawyer)
      .filter((l) => l.id === auth.user.lawyer_id)
  }
  return props.caseLawyers.map((cl) => cl.lawyer)
})
/** 是否本案负责人（主办律师或管理员）：核准/出账/收款/减免/冲正 */
const canManage = computed(() => {
  const user = auth.user
  if (!user) return false
  if (user.is_staff) return true
  return props.caseLawyers.some(
    (cl) => cl.role === 'lead' && cl.lawyer.id === user.lawyer_id)
})
/** 是否可删除某条待核准工时/费用（本人或负责人） */
const canEditEntry = (row) => {
  if (row.status !== 'pending') return false
  if (canManage.value) return true
  return auth.user && row.lawyer === auth.user.lawyer_id
}
const isHourly = computed(() => agreement.value?.fee_type === 'hourly')
const approvedTimeEntries = computed(() =>
  timeEntries.value.filter((e) => e.status === 'approved' && e.hourly_rate))
const approvedExpenses = computed(() =>
  expenses.value.filter((e) => e.status === 'approved'))
const unbilledTotal = computed(() =>
  Number(summary.value.unbilled_time_amount || 0) +
  Number(summary.value.unbilled_expense_amount || 0))
/** 固定收费已出账期款合计（不含已冲正账单） */
const fixedBilled = computed(() =>
  bills.value
    .filter((b) => b.status !== 'void')
    .flatMap((b) => b.lines)
    .filter((l) => l.line_type === 'fixed')
    .reduce((s, l) => s + Number(l.amount), 0))
const fixedRemaining = computed(() =>
  agreement.value?.fee_type === 'fixed'
    ? Number(agreement.value.fixed_amount) - fixedBilled.value
    : 0)
const billTotal = computed(() => {
  const t = billForm.selectedEntries.reduce((s, e) => s + Number(e.amount), 0)
  const x = billForm.selectedExpenses.reduce((s, e) => s + Number(e.amount), 0)
  const f = billForm.fixed_lines.reduce((s, l) => s + Number(l.amount || 0), 0)
  return t + x + f
})

const fmt = (n) =>
  Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const workStatusType = (s) => ({ pending: 'warning', approved: 'success', billed: 'info' }[s])
const billStatusType = (s) =>
  ({ open: 'primary', partial: 'warning', paid: 'success', void: 'info' }[s])

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/cases/${props.caseId}/finance/`)
    agreement.value = res.data.agreement
    rates.value = res.data.rates
    timeEntries.value = res.data.time_entries
    expenses.value = res.data.expenses
    bills.value = res.data.bills
    summary.value = res.data.summary
    if (currentBill.value) {
      currentBill.value = res.data.bills.find((b) => b.id === currentBill.value.id) || null
    }
  } finally {
    loading.value = false
  }
}

/* ---------- 收费约定与费率 ---------- */
function openAgreementDialog() {
  if (agreement.value) {
    Object.assign(agreementForm, {
      fee_type: agreement.value.fee_type,
      fixed_amount: agreement.value.fixed_amount ? Number(agreement.value.fixed_amount) : null,
      notes: agreement.value.notes || '',
    })
  } else {
    Object.assign(agreementForm, { fee_type: 'hourly', fixed_amount: null, notes: '' })
  }
  agreementDialog.value = true
}

async function saveAgreement() {
  if (agreementForm.fee_type === 'fixed' && !agreementForm.fixed_amount) {
    ElMessage.warning('请填写固定收费总额')
    return
  }
  const payload = { case: Number(props.caseId), ...agreementForm }
  if (agreement.value) {
    await api.patch(`/fee-agreements/${agreement.value.id}/`, payload)
  } else {
    await api.post('/fee-agreements/', payload)
  }
  ElMessage.success('收费约定已保存')
  agreementDialog.value = false
  load()
}

function openRateDialog() {
  Object.assign(rateForm, { lawyer: null, hourly_rate: null, effective_date: today })
  rateDialog.value = true
}

async function saveRate() {
  if (!rateForm.lawyer || !rateForm.hourly_rate || !rateForm.effective_date) {
    ElMessage.warning('律师、费率和生效日期必填')
    return
  }
  await api.post('/case-rates/', { case: Number(props.caseId), ...rateForm })
  ElMessage.success('费率已保存，仅影响生效日之后提交的工时')
  rateDialog.value = false
  load()
}

/* ---------- 工时与费用 ---------- */
function defaultLawyer() {
  return lawyerOptions.value.length === 1 ? lawyerOptions.value[0].id : null
}

function openTimeDialog() {
  Object.assign(timeForm, {
    lawyer: defaultLawyer(), work_date: today, hours: 1, description: '',
  })
  timeDialog.value = true
}

function openExpenseDialog() {
  Object.assign(expenseForm, {
    lawyer: defaultLawyer(), expense_date: today, category: 'court_fee',
    amount: null, description: '',
  })
  expenseDialog.value = true
}

async function saveTimeEntry() {
  if (!timeForm.lawyer || !timeForm.work_date || !timeForm.description) {
    ElMessage.warning('律师、日期和工作内容必填')
    return
  }
  await api.post('/time-entries/', { case: Number(props.caseId), ...timeForm })
  ElMessage.success('工时已提交，待负责人核准')
  timeDialog.value = false
  load()
}

async function saveExpense() {
  if (!expenseForm.lawyer || !expenseForm.expense_date || !expenseForm.amount
      || !expenseForm.description) {
    ElMessage.warning('代垫人、日期、金额和说明必填')
    return
  }
  await api.post('/expenses/', { case: Number(props.caseId), ...expenseForm })
  ElMessage.success('费用已提交，待负责人核准')
  expenseDialog.value = false
  Object.assign(expenseForm, {
    lawyer: defaultLawyer(), expense_date: today, category: 'court_fee', amount: null, description: '',
  })
  load()
}

async function approve(url, row) {
  await api.post(`${url}${row.id}/approve/`)
  ElMessage.success('已核准')
  load()
}

async function reject(url, row) {
  await api.post(`${url}${row.id}/reject/`)
  ElMessage.success('已退回待核准')
  load()
}

async function delEntry(url, row) {
  await api.delete(`${url}${row.id}/`)
  ElMessage.success('已删除')
  load()
}

/* ---------- 账单 ---------- */
function openBillDialog() {
  billForm.title = `第${bills.value.filter((b) => b.status !== 'void').length + 1}期`
  billForm.issue_date = today
  billForm.due_date = null
  billForm.selectedEntries = []
  billForm.selectedExpenses = []
  billForm.fixed_lines = isHourly.value ? [] : [{ description: '', amount: null }]
  billDialog.value = true
}

function addFixedLine() {
  billForm.fixed_lines.push({ description: '', amount: null })
}

async function createBill() {
  const fixedLines = billForm.fixed_lines.filter((l) => l.description && l.amount)
  const fixedSum = fixedLines.reduce((s, l) => s + Number(l.amount), 0)
  if (agreement.value?.fee_type === 'fixed' && fixedSum > fixedRemaining.value) {
    ElMessage.warning(`固定期款合计超出剩余可出额度 ¥${fmt(fixedRemaining.value)}`)
    return
  }
  await api.post('/bills/', {
    case: Number(props.caseId),
    title: billForm.title,
    issue_date: billForm.issue_date,
    due_date: billForm.due_date,
    time_entry_ids: billForm.selectedEntries.map((e) => e.id),
    expense_ids: billForm.selectedExpenses.map((e) => e.id),
    fixed_lines: fixedLines,
  })
  ElMessage.success('账单已生成')
  billDialog.value = false
  load()
}

function openBillDetail(row) {
  currentBill.value = row
  billDetailDialog.value = true
}

function openBillById(id) {
  const bill = bills.value.find((b) => b.id === id)
  if (bill) openBillDetail(bill)
}

function openPaymentDialog(row) {
  currentBill.value = row
  Object.assign(paymentForm, {
    amount: Number(row.outstanding), received_date: today, method: 'bank', notes: '',
  })
  paymentDialog.value = true
}

async function savePayment() {
  if (!paymentForm.amount || !paymentForm.received_date) {
    ElMessage.warning('收款金额和日期必填')
    return
  }
  await api.post('/payments/', { bill: currentBill.value.id, ...paymentForm })
  ElMessage.success('收款已登记')
  paymentDialog.value = false
  load()
}

async function reversePayment(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      `将以等额负数记录红冲该笔收款 ¥${fmt(row.amount)}，原记录保留。请输入红冲原因：`,
      '收款红冲',
      { confirmButtonText: '确认红冲', cancelButtonText: '取消', inputPlaceholder: '红冲原因' },
    )
    await api.post(`/payments/${row.id}/reverse/`, { reason: value })
    ElMessage.success('已红冲')
    load()
  } catch (e) {
    // 用户取消
  }
}

function openReductionDialog(row) {
  currentBill.value = row
  Object.assign(reductionForm, {
    amount: Number(row.reduction_amount), reason: row.reduction_reason || '',
  })
  reductionDialog.value = true
}

async function saveReduction() {
  if (reductionForm.amount > 0 && !reductionForm.reason) {
    ElMessage.warning('请填写减免原因')
    return
  }
  await api.post(`/bills/${currentBill.value.id}/reduction/`, reductionForm)
  ElMessage.success('减免已保存')
  reductionDialog.value = false
  load()
}

async function voidBill(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      `账单 ${row.bill_number} 冲正后将作废，已收款 ¥${fmt(row.received_amount)} 将自动生成退款记录，` +
      `明细中的工时/费用释放回已核准状态。请输入冲正原因：`,
      '账单冲正',
      { confirmButtonText: '确认冲正', cancelButtonText: '取消', inputPlaceholder: '冲正原因' },
    )
    await api.post(`/bills/${row.id}/void/`, { reason: value })
    ElMessage.success('账单已冲正')
    load()
  } catch (e) {
    // 用户取消
  }
}

async function delBill(row) {
  await api.delete(`/bills/${row.id}/`)
  ElMessage.success('账单已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.fin-summary { display: flex; gap: 12px; margin-bottom: 16px; }
.stat {
  flex: 1; background: #fff; border: 1px solid #ebeef5; border-radius: 4px;
  padding: 12px 16px;
}
.stat.muted { opacity: 0.65; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 20px; font-weight: 600; margin-top: 4px; }
.stat-value.green { color: #67c23a; }
.stat-value.orange { color: #e6a23c; }
.stat-sub { color: #909399; font-size: 12px; margin-top: 4px; }
.fin-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.section-bar {
  display: flex; justify-content: space-between; align-items: center;
  margin: 12px 0 8px;
}
.section-title { font-weight: 600; font-size: 14px; }
.pick-title { font-weight: 600; font-size: 13px; margin: 14px 0 8px; }
.fixed-line { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.bill-total { text-align: right; margin-top: 12px; font-size: 14px; }
.sub { color: #909399; font-size: 12px; }
.reduction { color: #f56c6c; }
.reversal { color: #f56c6c; }
</style>
