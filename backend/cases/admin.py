from django.contrib import admin

from .models import (ArchiveVersion, Case, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, PendingItem,
                     ReopenRequest, StageLog)


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


class PendingItemInline(admin.TabularInline):
    model = PendingItem
    extra = 0
    readonly_fields = ('kind', 'ref_id', 'item_key', 'title', 'detail',
                       'disposition', 'disposition_note')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ArchiveVersion)
class ArchiveVersionAdmin(admin.ModelAdmin):
    list_display = ('case', 'version_no', 'status', 'prepared_by',
                    'reviewer', 'sealed_at')
    list_filter = ('status',)
    search_fields = ('case__case_number', 'case__title', 'prepared_by', 'reviewer')
    readonly_fields = ('fingerprint', 'fingerprint_state', 'snapshot')
    inlines = [PendingItemInline]


@admin.register(ReopenRequest)
class ReopenRequestAdmin(admin.ModelAdmin):
    list_display = ('case', 'reason_type', 'applicant', 'status',
                    'approver', 'decided_at')
    list_filter = ('status', 'reason_type')
    search_fields = ('case__case_number', 'applicant', 'approver', 'reason')
    readonly_fields = ('decided_at',)


admin.site.register([Hearing, StageLog, Material, Deadline])
