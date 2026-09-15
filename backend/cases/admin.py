from django.contrib import admin

from .models import (Case, CaseLawyer, CaseParty, Deadline, Hearing, Lawyer,
                     Material, Party, PartyAlias, PartyMergeRecord, StageLog)


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
    list_display = ('name', 'party_type', 'id_number', 'phone', 'source_system',
                    'merged_into', 'merged_at')
    list_filter = ('party_type', 'source_system')
    search_fields = ('name', 'id_number', 'phone')
    inlines = [CasePartyInline]


@admin.register(PartyAlias)
class PartyAliasAdmin(admin.ModelAdmin):
    list_display = ('name', 'party', 'source_system', 'source_party', 'created_at')
    search_fields = ('name', 'party__name')


@admin.register(PartyMergeRecord)
class PartyMergeRecordAdmin(admin.ModelAdmin):
    list_display = ('source_name', 'master_party', 'source_system', 'operator', 'created_at')
    search_fields = ('source_name', 'master_party__name', 'operator')
    readonly_fields = ('source_snapshot', 'field_resolutions', 'relation_resolutions',
                       'warnings_confirmed', 'created_at')


admin.site.register([Hearing, StageLog, Material, Deadline])
