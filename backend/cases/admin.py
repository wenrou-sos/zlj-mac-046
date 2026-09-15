from django.contrib import admin

from .models import (Case, CaseLawyer, CaseParty, Deadline, DeadlineEvent,
                     DeadlineRule, DeadlineVersion, Hearing, Holiday, Lawyer,
                     Material, Party, Reminder, StageLog)


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


@admin.register(DeadlineRule)
class DeadlineRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_type', 'duration_days', 'day_type',
                    'holiday_postpone', 'active')
    list_filter = ('event_type', 'day_type', 'holiday_postpone', 'active')
    search_fields = ('name',)


@admin.register(DeadlineEvent)
class DeadlineEventAdmin(admin.ModelAdmin):
    list_display = ('case', 'title', 'event_type', 'event_date', 'status')
    list_filter = ('event_type', 'status')
    search_fields = ('title', 'case__case_number')


class DeadlineVersionInline(admin.TabularInline):
    model = DeadlineVersion
    extra = 0
    readonly_fields = ('version', 'change_type', 'reason', 'snapshot', 'created_at')
    can_delete = False


class ReminderInline(admin.TabularInline):
    model = Reminder
    extra = 0
    readonly_fields = ('recipient', 'recipient_role', 'kind', 'scheduled_at',
                       'status', 'attempts', 'dedupe_key')
    can_delete = False


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ('title', 'case', 'due_date', 'owner', 'reviewer',
                    'source', 'lifecycle', 'is_done')
    list_filter = ('source', 'lifecycle', 'is_done', 'deadline_type')
    search_fields = ('title', 'case__case_number')
    inlines = [DeadlineVersionInline, ReminderInline]


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('deadline', 'recipient', 'recipient_role', 'kind',
                    'scheduled_at', 'status', 'attempts')
    list_filter = ('kind', 'status', 'recipient_role')
    search_fields = ('deadline__title', 'recipient__name')


admin.site.register([Hearing, StageLog, Material, Holiday])
