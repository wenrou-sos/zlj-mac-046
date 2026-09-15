from django.contrib import admin

from .models import (Case, CaseHandover, CaseLawyer, CaseParty, Deadline,
                     HandoverItem, HandoverLog, Hearing, Lawyer, Material,
                     Party, StageLog)


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


class HandoverItemInline(admin.TabularInline):
    model = HandoverItem
    extra = 0
    readonly_fields = ('item_type', 'ref_id', 'title', 'detail', 'change_flag')
    fields = ('item_type', 'title', 'detail', 'destination', 'checked', 'change_flag')


class HandoverLogInline(admin.TabularInline):
    model = HandoverLog
    extra = 0
    readonly_fields = ('action', 'actor_lawyer', 'actor_name', 'note', 'created_at')


@admin.register(CaseHandover)
class CaseHandoverAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'from_lawyer', 'to_lawyer', 'status', 'created_at', 'completed_at')
    list_filter = ('status',)
    search_fields = ('case__case_number', 'case__title',
                     'from_lawyer__name', 'to_lawyer__name')
    inlines = [HandoverItemInline, HandoverLogInline]
