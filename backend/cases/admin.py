from django.contrib import admin

from .models import (Bill, BillLine, Case, CaseLawyer, CaseParty, CaseRate,
                     Deadline, Expense, FeeAgreement, Hearing, Lawyer,
                     Material, Party, Payment, StageLog, TimeEntry)


class CasePartyInline(admin.TabularInline):
    model = CaseParty
    extra = 1


class CaseLawyerInline(admin.TabularInline):
    model = CaseLawyer
    extra = 1


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('case_number', 'title', 'case_type', 'stage', 'court', 'filed_date')
    list_filter = ('case_type', 'stage')
    search_fields = ('case_number', 'title')
    inlines = [CasePartyInline, CaseLawyerInline]


@admin.register(Lawyer)
class LawyerAdmin(admin.ModelAdmin):
    list_display = ('name', 'bar_number', 'title', 'phone')
    search_fields = ('name', 'bar_number')


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'party_type', 'id_number', 'phone')
    list_filter = ('party_type',)
    search_fields = ('name', 'id_number')


admin.site.register([Hearing, StageLog, Material, Deadline])


class BillLineInline(admin.TabularInline):
    model = BillLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(FeeAgreement)
class FeeAgreementAdmin(admin.ModelAdmin):
    list_display = ('case', 'fee_type', 'fixed_amount')
    list_filter = ('fee_type',)


@admin.register(CaseRate)
class CaseRateAdmin(admin.ModelAdmin):
    list_display = ('case', 'lawyer', 'hourly_rate', 'effective_date')
    list_filter = ('case',)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('case', 'lawyer', 'work_date', 'hours', 'hourly_rate', 'status')
    list_filter = ('status', 'case')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('case', 'lawyer', 'expense_date', 'category', 'amount', 'status')
    list_filter = ('status', 'category')


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'case', 'title', 'issue_date', 'status',
                    'reduction_amount')
    list_filter = ('status',)
    inlines = [BillLineInline, PaymentInline]


admin.site.register(Payment)
