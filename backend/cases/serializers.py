from datetime import date

from rest_framework import serializers

from .models import (Case, CaseLawyer, CaseParty, Deadline, DeadlineEvent,
                     DeadlineRule, DeadlineVersion, Hearing, Holiday, Lawyer,
                     Material, Party, Reminder, StageLog)
from .services import assign_owner_and_reviewer, create_version, sync_reminders


class LawyerSerializer(serializers.ModelSerializer):
    title_display = serializers.CharField(source='get_title_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Lawyer
        fields = '__all__'

    def get_case_count(self, obj):
        return obj.cases.exclude(stage='closed').count()


class PartySerializer(serializers.ModelSerializer):
    party_type_display = serializers.CharField(source='get_party_type_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = '__all__'

    def get_case_count(self, obj):
        return obj.cases.count()


class CasePartySerializer(serializers.ModelSerializer):
    party = PartySerializer(read_only=True)
    party_id = serializers.PrimaryKeyRelatedField(
        queryset=Party.objects.all(), source='party', write_only=True)
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CaseParty
        fields = ['id', 'case', 'party', 'party_id', 'role', 'role_display', 'is_client']

    def validate(self, attrs):
        qs = CaseParty.objects.filter(
            case=attrs['case'], party=attrs['party'], role=attrs['role'])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'party_id': '该当事人已以此诉讼地位存在于本案中'})
        return attrs


class CaseLawyerSerializer(serializers.ModelSerializer):
    lawyer = LawyerSerializer(read_only=True)
    lawyer_id = serializers.PrimaryKeyRelatedField(
        queryset=Lawyer.objects.all(), source='lawyer', write_only=True)
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = CaseLawyer
        fields = ['id', 'case', 'lawyer', 'lawyer_id', 'role', 'role_display']

    def validate(self, attrs):
        qs = CaseLawyer.objects.filter(case=attrs['case'], lawyer=attrs['lawyer'])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({'lawyer_id': '该律师已承办本案'})
        return attrs


class HearingSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)

    class Meta:
        model = Hearing
        fields = '__all__'


class StageLogSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)

    class Meta:
        model = StageLog
        fields = '__all__'


class MaterialSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Material
        fields = '__all__'


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = '__all__'


class DeadlineRuleSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    day_type_display = serializers.CharField(source='get_day_type_display', read_only=True)
    start_timing_display = serializers.CharField(source='get_start_timing_display', read_only=True)
    owner_role_display = serializers.CharField(source='get_owner_role_display', read_only=True)
    reviewer_role_display = serializers.CharField(source='get_reviewer_role_display', read_only=True)
    deadline_type_display = serializers.CharField(source='get_deadline_type_display', read_only=True)

    class Meta:
        model = DeadlineRule
        fields = '__all__'


class DeadlineEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)

    class Meta:
        model = DeadlineEvent
        fields = '__all__'
        read_only_fields = ['status', 'revoked_reason', 'revoked_at']

class DeadlineVersionListSerializer(serializers.ModelSerializer):
    change_type_display = serializers.CharField(source='get_change_type_display', read_only=True)

    class Meta:
        model = DeadlineVersion
        fields = ['id', 'version', 'change_type', 'change_type_display',
                  'reason', 'snapshot', 'created_at']


class ReminderSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    recipient_role_display = serializers.CharField(source='get_recipient_role_display', read_only=True)
    deadline_title = serializers.CharField(source='deadline.title', read_only=True)
    deadline_due_date = serializers.DateField(source='deadline.due_date', read_only=True)
    case_id = serializers.IntegerField(source='deadline.case_id', read_only=True)
    case_title = serializers.CharField(source='deadline.case.title', read_only=True)
    recipient_name = serializers.CharField(source='recipient.name', read_only=True)

    class Meta:
        model = Reminder
        fields = '__all__'
        read_only_fields = ['deadline', 'recipient', 'recipient_role', 'kind', 'scheduled_at',
                            'sent_at', 'confirmed_at', 'status', 'attempts', 'next_retry_at',
                            'last_error', 'dedupe_key']


class DeadlineSerializer(serializers.ModelSerializer):
    deadline_type_display = serializers.CharField(source='get_deadline_type_display', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    days_left = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source='owner.name', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.name', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    lifecycle_display = serializers.CharField(source='get_lifecycle_display', read_only=True)
    versions = DeadlineVersionListSerializer(many=True, read_only=True)

    class Meta:
        model = Deadline
        fields = '__all__'

    def get_days_left(self, obj):
        return (obj.due_date - date.today()).days

    def _case(self):
        if self.instance:
            return self.instance.case
        return self.initial_data.get('case') and Case.objects.filter(
            pk=self.initial_data.get('case')).first()

    def validate(self, attrs):
        if self.partial and not attrs:
            return attrs

        case = self.instance.case if self.instance else attrs.get('case')
        if not self.instance and not case:
            raise serializers.ValidationError({'case': '请选择案件'})

        owner = attrs.get('owner', getattr(self.instance, 'owner', None))
        reviewer = attrs.get('reviewer', getattr(self.instance, 'reviewer', None))
        if not owner:
            default_owner, default_reviewer = assign_owner_and_reviewer(case)
            if not default_owner:
                raise serializers.ValidationError({'owner': '请选择负责人，或先为案件配置承办律师'})
            attrs['owner'] = owner = default_owner
            if not reviewer:
                attrs['reviewer'] = default_reviewer
        if not reviewer:
            raise serializers.ValidationError({'reviewer': '请选择复核人'})
        if owner == reviewer:
            raise serializers.ValidationError({'reviewer': '负责人和复核人不能为同一人'})

        due_date = attrs.get('due_date', getattr(self.instance, 'due_date', None))
        if not due_date:
            raise serializers.ValidationError({'due_date': '请选择截止日期'})

        if self.instance and self.instance.source == 'generated':
            protected = {'due_date', 'title', 'deadline_type', 'rule', 'event',
                         'remind_days', 'escalate_days', 'basis_text'}
            changed = [key for key in attrs if key in protected]
            if changed:
                raise serializers.ValidationError(
                    '规则生成期限不能直接改写；请更正起算事件或调整律所规则后走影响确认')
        return attrs

    def create(self, validated_data):
        validated_data['source'] = 'manual'
        deadline = super().create(validated_data)
        if not deadline.basis_text:
            deadline.basis_text = f'人工登记：{deadline.title}，截止日期由承办人指定。'
            deadline.save(update_fields=['basis_text'])
        create_version(deadline, 'created', '人工登记期限')
        sync_reminders(deadline)
        return deadline

    def update(self, instance, validated_data):
        tracked = {'title', 'deadline_type', 'due_date', 'remind_days', 'escalate_days',
                   'owner', 'reviewer', 'basis_text', 'notes'}
        meaningful = {key: value for key, value in validated_data.items() if key in tracked}
        if meaningful:
            create_version(instance, 'manual_update', '人工编辑期限')
        reopening = instance.is_done and validated_data.get('is_done') is False
        was_done = instance.is_done
        deadline = super().update(instance, validated_data)
        if validated_data.get('is_done') is True and not was_done:
            from django.utils import timezone
            deadline.done_at = timezone.now()
            deadline.save(update_fields=['done_at'])
            deadline.reminders.filter(status__in=['pending', 'failed']).update(status='cancelled')
        elif reopening:
            deadline.done_at = None
            deadline.save(update_fields=['done_at'])
            sync_reminders(deadline)
        elif meaningful:
            sync_reminders(deadline)
        return deadline


class CaseListSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    case_type_display = serializers.CharField(source='get_case_type_display', read_only=True)
    case_lawyers = CaseLawyerSerializer(source='caselawyer_set', many=True, read_only=True)
    case_parties = CasePartySerializer(source='caseparty_set', many=True, read_only=True)
    pending_deadline_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'case_type_display',
                  'stage', 'stage_display', 'cause', 'court', 'filed_date',
                  'amount', 'case_lawyers', 'case_parties',
                  'pending_deadline_count', 'created_at']

    def get_pending_deadline_count(self, obj):
        return obj.deadlines.filter(is_done=False, lifecycle='active').count()


class CaseDetailSerializer(CaseListSerializer):
    hearings = HearingSerializer(many=True, read_only=True)
    stage_logs = StageLogSerializer(many=True, read_only=True)
    materials = MaterialSerializer(many=True, read_only=True)
    deadlines = DeadlineSerializer(many=True, read_only=True)
    deadline_events = DeadlineEventSerializer(many=True, read_only=True)

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials',
            'deadlines', 'deadline_events']


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']
