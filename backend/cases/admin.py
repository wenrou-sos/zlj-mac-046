from django.contrib import admin

from .models import (AuditLog, Case, CaseAccess, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog, UserProfile)


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


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'lawyer')
    list_filter = ('role',)
    search_fields = ('user__username',)
    autocomplete_fields = ('lawyer',)


@admin.register(CaseAccess)
class CaseAccessAdmin(admin.ModelAdmin):
    list_display = ('case', 'user', 'role', 'source', 'expires_at',
                    'revoked', 'granted_at')
    list_filter = ('role', 'source', 'revoked')
    search_fields = ('user__username', 'case__case_number', 'case__title')
    autocomplete_fields = ('case', 'user')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target_user', 'case', 'ip')
    list_filter = ('action',)
    search_fields = ('actor__username', 'detail')
    date_hierarchy = 'created_at'


admin.site.register([Hearing, StageLog, Material, Deadline])
