from django.contrib import admin

from .models import (Case, CaseLawyer, CaseParty, Deadline, Hearing, Lawyer,
                     Material, MaterialReview, MaterialSubmission,
                     MaterialVersion, Party, StageLog, SubmissionItem,
                     SubmissionReceipt)


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


class MaterialVersionInline(admin.TabularInline):
    model = MaterialVersion
    extra = 0
    fields = ('version_no', 'file', 'uploaded_by', 'is_final',
              'finalized_by', 'created_at')
    readonly_fields = ('version_no', 'created_at')


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'case', 'category', 'status', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('name',)
    inlines = [MaterialVersionInline]


class SubmissionItemInline(admin.TabularInline):
    model = SubmissionItem
    extra = 0
    fields = ('material_name', 'version_no', 'file_name', 'copies', 'pages')


class SubmissionReceiptInline(admin.TabularInline):
    model = SubmissionReceipt
    extra = 0
    fields = ('receipt_type', 'receipt_no', 'receiver_name',
              'receipt_date', 'file', 'note')


@admin.register(MaterialSubmission)
class MaterialSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'submitted_to', 'method',
                    'submit_date', 'status', 'created_by')
    list_filter = ('status', 'method')
    search_fields = ('submitted_to',)
    inlines = [SubmissionItemInline, SubmissionReceiptInline]


@admin.register(MaterialVersion)
class MaterialVersionAdmin(admin.ModelAdmin):
    list_display = ('material', 'version_no', 'file_name', 'uploaded_by',
                    'is_final', 'is_backfilled', 'created_at')
    list_filter = ('is_final', 'is_backfilled')
    search_fields = ('file_name', 'material__name')
    readonly_fields = ('version_no', 'file_name', 'file_size', 'file_hash',
                       'finalized_at', 'created_at')


@admin.register(MaterialReview)
class MaterialReviewAdmin(admin.ModelAdmin):
    list_display = ('version', 'author', 'result', 'created_at')
    list_filter = ('result',)


admin.site.register([Hearing, StageLog, Deadline])
