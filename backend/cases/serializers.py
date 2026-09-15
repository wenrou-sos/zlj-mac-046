from datetime import date

from rest_framework import serializers

from .models import (Case, CaseLawyer, CaseParty, ConflictReview,
                     ConflictReviewLog, ConflictReviewMaterial, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog)


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

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials', 'deadlines']


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']


class LawyerBriefSerializer(serializers.ModelSerializer):
    title_display = serializers.CharField(source='get_title_display', read_only=True)

    class Meta:
        model = Lawyer
        fields = ['id', 'name', 'title', 'title_display']


class ConflictReviewMaterialSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.name', read_only=True)

    class Meta:
        model = ConflictReviewMaterial
        fields = ['id', 'name', 'material_type', 'source', 'remark',
                  'uploaded_by', 'uploaded_by_name', 'uploaded_at']
        read_only_fields = ['uploaded_by', 'uploaded_at']


class ConflictReviewLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = ConflictReviewLog
        fields = ['id', 'action', 'action_display', 'actor', 'actor_name',
                  'detail', 'created_at']
        read_only_fields = fields


class ConflictReviewListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    risk_level_display = serializers.SerializerMethodField()
    party_name = serializers.CharField(source='party.name', read_only=True)
    party_type_display = serializers.CharField(source='party.get_party_type_display', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True)
    case_title = serializers.CharField(source='case.title', read_only=True)
    proposed_role_display = serializers.CharField(source='get_proposed_role_display', read_only=True)
    applicant_name = serializers.CharField(source='applicant.name', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.name', read_only=True)
    used_by_name = serializers.CharField(source='used_by.name', read_only=True, default=None)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = ConflictReview
        fields = ['id', 'review_number', 'case', 'case_number', 'case_title',
                  'party', 'party_name', 'party_type_display',
                  'proposed_role', 'proposed_role_display', 'proposed_is_client',
                  'applicant', 'applicant_name', 'reviewer', 'reviewer_name',
                  'risk_level', 'risk_level_display', 'has_prohibited', 'needs_exception',
                  'status', 'status_display', 'is_active',
                  'exception_expire_date', 'used_at', 'used_by_name',
                  'created_at', 'decided_at']

    def get_risk_level_display(self, obj):
        return {'high': '高风险', 'medium': '需关注', 'low': '低风险'}.get(obj.risk_level, obj.risk_level)

    def get_is_active(self, obj):
        return obj.is_active_approval


class ConflictReviewSerializer(ConflictReviewListSerializer):
    materials = ConflictReviewMaterialSerializer(many=True, read_only=True)
    logs = ConflictReviewLogSerializer(many=True, read_only=True)
    snapshot = serializers.JSONField(read_only=True)
    superseded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    prior_review_id = serializers.IntegerField(write_only=True, required=False,
                                               help_text='退回补充/重新复核所基于的原复核单')

    class Meta(ConflictReviewListSerializer.Meta):
        fields = ConflictReviewListSerializer.Meta.fields + [
            'apply_remark', 'decision_remark', 'exception_basis',
            'decided_at', 'used_by', 'used_at', 'superseded_by',
            'snapshot', 'materials', 'logs', 'prior_review_id']
        read_only_fields = ['status', 'decision_remark', 'exception_basis',
                            'exception_expire_date', 'decided_at', 'used_at',
                            'used_by', 'superseded_by']

    def validate(self, attrs):
        prior_id = attrs.pop('prior_review_id', None)
        self._prior_review = None
        if prior_id is not None:
            prior = ConflictReview.objects.filter(pk=prior_id).first()
            if not prior:
                raise serializers.ValidationError({'prior_review_id': '原复核单不存在'})
            self._prior_review = prior
        return attrs


class ConflictReviewCreateSerializer(serializers.Serializer):
    """发起冲突复核申请：入参为拟承接关系，风险快照由服务端冻结。"""
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    party = serializers.PrimaryKeyRelatedField(queryset=Party.objects.all())
    proposed_role = serializers.ChoiceField(choices=CaseParty.ROLE_CHOICES)
    proposed_is_client = serializers.BooleanField(required=False, default=False)
    reviewer = serializers.PrimaryKeyRelatedField(
        queryset=Lawyer.objects.all(), required=False, allow_null=True)
    apply_remark = serializers.CharField(required=False, allow_blank=True, default='')
    materials = ConflictReviewMaterialSerializer(many=True, required=False)
    prior_review = serializers.PrimaryKeyRelatedField(
        queryset=ConflictReview.objects.all(), required=False, allow_null=True)

    def validate_materials(self, value):
        if not value:
            return value
        for m in value:
            if not m.get('name'):
                raise serializers.ValidationError('每份材料均须填写材料名称')
        return value


class ConflictDecisionSerializer(serializers.Serializer):
    """复核人作出批准 / 拒绝 / 退回补充材料决定。"""
    decision = serializers.ChoiceField(choices=['approve', 'reject', 'return'])
    decision_remark = serializers.CharField(required=False, allow_blank=True, default='')
    exception_basis = serializers.CharField(required=False, allow_blank=True, default='')
    exception_expire_date = serializers.DateField(required=False, allow_null=True)
    resubmit_required = serializers.BooleanField(required=False, default=False)
