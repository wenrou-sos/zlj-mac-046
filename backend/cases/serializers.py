from datetime import date

from rest_framework import serializers

from .models import (Case, CaseHandover, CaseLawyer, CaseParty, Deadline,
                     HandoverItem, HandoverLog, Hearing, Lawyer, Material,
                     Party, StageLog)


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


class DeadlineSerializer(serializers.ModelSerializer):
    deadline_type_display = serializers.CharField(source='get_deadline_type_display', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = Deadline
        fields = '__all__'

    def get_days_left(self, obj):
        return (obj.due_date - date.today()).days


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
        return obj.deadlines.filter(is_done=False).count()


class CaseDetailSerializer(CaseListSerializer):
    hearings = HearingSerializer(many=True, read_only=True)
    stage_logs = StageLogSerializer(many=True, read_only=True)
    materials = MaterialSerializer(many=True, read_only=True)
    deadlines = DeadlineSerializer(many=True, read_only=True)
    active_handover = serializers.SerializerMethodField()
    handover_history = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials', 'deadlines',
            'active_handover', 'handover_history']

    def get_active_handover(self, obj):
        h = obj.handovers.filter(
            status__in=['draft', 'pending', 'returned']).order_by('-id').first()
        if not h:
            return None
        return {
            'id': h.id,
            'status': h.status,
            'status_display': h.get_status_display(),
            'from_lawyer_id': h.from_lawyer_id,
            'from_lawyer_name': h.from_lawyer.name,
            'to_lawyer_id': h.to_lawyer_id,
            'to_lawyer_name': h.to_lawyer.name,
        }

    def get_handover_history(self, obj):
        rows = []
        for h in obj.handovers.filter(
                status__in=['completed', 'canceled']).select_related(
                'from_lawyer', 'to_lawyer'):
            rows.append({
                'id': h.id,
                'status': h.status,
                'status_display': h.get_status_display(),
                'from_lawyer_name': h.from_lawyer.name,
                'to_lawyer_name': h.to_lawyer.name,
                'reason': h.reason,
                'completed_at': h.completed_at,
                'created_at': h.created_at,
            })
        return rows


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']


class HandoverItemSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    destination_display = serializers.CharField(source='get_destination_display', read_only=True)
    change_flag_display = serializers.CharField(source='get_change_flag_display', read_only=True)

    class Meta:
        model = HandoverItem
        fields = ['id', 'item_type', 'item_type_display', 'ref_id', 'title', 'detail',
                  'due_date', 'hearing_time', 'is_overdue', 'destination',
                  'destination_display', 'checked', 'check_note',
                  'change_flag', 'change_flag_display', 'created_at', 'updated_at']
        read_only_fields = ['item_type', 'ref_id', 'title', 'detail', 'due_date',
                            'hearing_time', 'is_overdue', 'change_flag']


class HandoverLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = HandoverLog
        fields = ['id', 'action', 'action_display', 'actor_name', 'note', 'created_at']


class HandoverListSerializer(serializers.ModelSerializer):
    """交接列表（不含条目明细）"""
    from_lawyer_name = serializers.CharField(source='from_lawyer.name', read_only=True)
    to_lawyer_name = serializers.CharField(source='to_lawyer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)
    case_stage = serializers.CharField(source='case.stage', read_only=True)
    pending_count = serializers.SerializerMethodField()
    stale = serializers.SerializerMethodField()

    class Meta:
        model = CaseHandover
        fields = ['id', 'case', 'case_number', 'case_title', 'case_stage',
                  'from_lawyer', 'from_lawyer_name', 'to_lawyer', 'to_lawyer_name',
                  'status', 'status_display', 'reason', 'pending_count', 'stale',
                  'submitted_at', 'completed_at', 'created_at']

    def get_pending_count(self, obj):
        return obj.items.exclude(change_flag='removed').count()

    def get_stale(self, obj):
        # 仅待核对状态需要防过期提示
        if obj.status != 'pending':
            return False
        from .handovers import diff_items
        return diff_items(obj)['stale']


class HandoverDetailSerializer(HandoverListSerializer):
    items = HandoverItemSerializer(many=True, read_only=True)
    logs = HandoverLogSerializer(many=True, read_only=True)
    active_items_count = serializers.SerializerMethodField()
    checked_count = serializers.SerializerMethodField()

    class Meta(HandoverListSerializer.Meta):
        fields = HandoverListSerializer.Meta.fields + [
            'items', 'logs', 'returned_reason', 'cancel_reason',
            'last_refreshed_at', 'updated_at',
            'active_items_count', 'checked_count']

    def get_active_items_count(self, obj):
        return obj.items.exclude(change_flag='removed').count()

    def get_checked_count(self, obj):
        return obj.items.exclude(change_flag='removed').filter(checked=True).count()


class HandoverCreateSerializer(serializers.Serializer):
    to_lawyer_id = serializers.PrimaryKeyRelatedField(
        queryset=Lawyer.objects.all(), required=False)
    to_lawyer = serializers.PrimaryKeyRelatedField(queryset=Lawyer.objects.all(), required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=200)
    submit = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        to = attrs.get('to_lawyer_id') or attrs.get('to_lawyer')
        if not to:
            raise serializers.ValidationError({'to_lawyer': '请选择接收人'})
        attrs['to_lawyer'] = to
        return attrs

