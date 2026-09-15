from datetime import date

from rest_framework import serializers

from .models import (ArchiveVersion, Case, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, PendingItem,
                     ReopenRequest, StageLog)


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
    archive = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'case_type_display',
                  'stage', 'stage_display', 'cause', 'court', 'filed_date',
                  'amount', 'case_lawyers', 'case_parties',
                  'pending_deadline_count', 'archive', 'created_at']

    def get_pending_deadline_count(self, obj):
        return obj.deadlines.filter(is_done=False).count()

    def get_archive(self, obj):
        return obj.archive_info()


class CaseDetailSerializer(CaseListSerializer):
    hearings = HearingSerializer(many=True, read_only=True)
    stage_logs = StageLogSerializer(many=True, read_only=True)
    materials = MaterialSerializer(many=True, read_only=True)
    deadlines = DeadlineSerializer(many=True, read_only=True)
    archive_versions = serializers.SerializerMethodField()
    reopen_requests = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials', 'deadlines',
            'archive_versions', 'reopen_requests']

    def get_archive_versions(self, obj):
        return ArchiveVersionListSerializer(obj.get_archive_versions(), many=True).data

    def get_reopen_requests(self, obj):
        return ReopenRequestSerializer(
            obj.reopen_requests.order_by('-id'), many=True).data


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']

    def validate_stage(self, value):
        # 结案必须走「结案归档-复核封存」流程，不能直接把阶段改成结案；
        # 已经是结案的案件允许保持结案状态（仅改其他字段）
        if value == 'closed' and not (self.instance and self.instance.stage == 'closed'):
            raise serializers.ValidationError(
                '结案请使用案件详情中的「结案归档」流程，经复核封存后自动进入结案')
        return value


class PendingItemSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    disposition_display = serializers.CharField(source='get_disposition_display', read_only=True)

    class Meta:
        model = PendingItem
        fields = ['id', 'kind', 'kind_display', 'ref_id', 'item_key', 'title',
                  'detail', 'disposition', 'disposition_display',
                  'disposition_note']


class ArchiveVersionListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = ArchiveVersion
        fields = ['id', 'version_no', 'status', 'status_display', 'closed_date',
                  'summary', 'prepared_by', 'submitted_by', 'submitted_at',
                  'reviewer', 'review_comment', 'sealed_at', 'reject_reason',
                  'pending_count', 'created_at']

    def get_pending_count(self, obj):
        return obj.pending_items.count()


class ArchiveVersionSerializer(ArchiveVersionListSerializer):
    pending_items = PendingItemSerializer(many=True, read_only=True)
    snapshot = serializers.JSONField(read_only=True)

    class Meta(ArchiveVersionListSerializer.Meta):
        fields = ArchiveVersionListSerializer.Meta.fields + [
            'pending_items', 'snapshot', 'fingerprint']


class ReopenRequestSerializer(serializers.ModelSerializer):
    reason_type_display = serializers.CharField(source='get_reason_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    next_stage_display = serializers.CharField(source='get_next_stage_display', read_only=True)
    archive_version_no = serializers.SerializerMethodField()

    class Meta:
        model = ReopenRequest
        fields = ['id', 'case', 'archive_version', 'archive_version_no',
                  'reason_type', 'reason_type_display', 'reason',
                  'applicant', 'status', 'status_display', 'approver',
                  'approval_comment', 'next_stage', 'next_stage_display',
                  'decided_at', 'created_at']

    def get_archive_version_no(self, obj):
        return obj.archive_version.version_no if obj.archive_version_id else None
