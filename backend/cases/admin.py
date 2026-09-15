from django.contrib import admin

from .models import (Case, CaseLawyer, CaseParty, ConflictReview,
                     ConflictReviewLog, ConflictReviewMaterial, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog)


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


class ConflictReviewMaterialInline(admin.TabularInline):
    model = ConflictReviewMaterial
    extra = 0
    readonly_fields = ('uploaded_by', 'uploaded_at')


class ConflictReviewLogInline(admin.TabularInline):
    model = ConflictReviewLog
    extra = 0
    readonly_fields = ('action', 'actor', 'actor_name', 'detail', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ConflictReview)
class ConflictReviewAdmin(admin.ModelAdmin):
    list_display = ('review_number', 'case', 'party', 'proposed_role',
                    'risk_level', 'status', 'applicant', 'reviewer',
                    'exception_expire_date', 'created_at')
    list_filter = ('status', 'risk_level', 'has_prohibited', 'needs_exception')
    search_fields = ('review_number', 'party__name', 'case__case_number', 'case__title')
    readonly_fields = ('review_number', 'snapshot', 'relationship_fingerprint',
                       'risk_level', 'has_prohibited', 'needs_exception',
                       'used_at', 'used_by', 'superseded_by', 'created_at', 'updated_at')
    inlines = [ConflictReviewMaterialInline, ConflictReviewLogInline]
