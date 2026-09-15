import hashlib
from datetime import date

from django.db import transaction
from rest_framework import serializers

from .models import (Case, CaseLawyer, CaseParty, Deadline, Hearing, Lawyer,
                     Material, MaterialReview, MaterialSubmission,
                     MaterialVersion, Party, StageLog, SubmissionItem,
                     SubmissionReceipt)


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


# ---------- 材料版本 / 审阅意见 ----------

MAX_UPLOAD_SIZE = 100 * 1024 * 1024


class MaterialReviewSerializer(serializers.ModelSerializer):
    result_display = serializers.CharField(source='get_result_display', read_only=True)
    author = serializers.CharField(required=True, allow_blank=False, max_length=50)

    class Meta:
        model = MaterialReview
        fields = ['id', 'version', 'author', 'result', 'result_display',
                  'comment', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'comment': {'required': True, 'allow_blank': False}}


class MaterialVersionSerializer(serializers.ModelSerializer):
    reviews = MaterialReviewSerializer(many=True, read_only=True)
    is_submitted = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MaterialVersion
        fields = ['id', 'material', 'version_no', 'file', 'file_url', 'file_name',
                  'file_size', 'file_hash', 'change_note', 'uploaded_by',
                  'is_backfilled', 'is_final', 'finalized_by', 'finalized_at',
                  'created_at', 'reviews', 'is_submitted']
        read_only_fields = ['id', 'version_no', 'file_name', 'file_size', 'file_hash',
                            'is_final', 'finalized_by', 'finalized_at', 'created_at']

    def get_is_submitted(self, obj):
        return obj.submission_items.exists()

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, f):
        if f.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError('附件不能超过 100MB')
        if f.size == 0:
            raise serializers.ValidationError('附件内容为空，上传失败')
        return f

    def validate(self, attrs):
        is_backfilled = bool(attrs.get('is_backfilled'))
        if not is_backfilled and not attrs.get('file'):
            raise serializers.ValidationError(
                {'file': '请选择附件；仅补录历史材料时允许暂缺附件'})
        if not attrs.get('uploaded_by'):
            raise serializers.ValidationError({'uploaded_by': '请填写上传人'})
        return attrs

    @staticmethod
    def _hash_upload(uploaded):
        sha = hashlib.sha256()
        for chunk in uploaded.chunks():
            sha.update(chunk)
        uploaded.seek(0)
        return sha.hexdigest()

    def create(self, validated_data):
        uploaded = validated_data.get('file')
        if uploaded is not None:
            validated_data['file_name'] = uploaded.name
            validated_data['file_size'] = uploaded.size
            validated_data['file_hash'] = self._hash_upload(uploaded)
        else:
            validated_data['file_name'] = ''
            validated_data['is_backfilled'] = True

        material = validated_data['material']
        instance = None
        try:
            with transaction.atomic():
                # 行锁内分配版本号：多人并发上传互不覆盖，由唯一约束兜底
                locked = Material.objects.select_for_update().get(pk=material.pk)
                last_no = (MaterialVersion.objects
                           .select_for_update()
                           .filter(material=locked)
                           .order_by('-version_no')
                           .values_list('version_no', flat=True)
                           .first()) or 0
                validated_data['version_no'] = last_no + 1
                instance = MaterialVersion(**validated_data)
                instance.save()  # 文件随实例一并落盘
        except Exception:
            # 任何失败都不能留下可用附件记录或孤儿文件
            if instance is not None and instance.file:
                instance.file.delete(save=False)
            if uploaded is not None:
                uploaded.close()
            raise
        return instance


# ---------- 提交回执 / 清单 / 批次 ----------

class SubmissionReceiptSerializer(serializers.ModelSerializer):
    receipt_type_display = serializers.CharField(
        source='get_receipt_type_display', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionReceipt
        fields = ['id', 'submission', 'receipt_type', 'receipt_type_display',
                  'receipt_no', 'receiver_name', 'receipt_date', 'file', 'file_url',
                  'file_name', 'note', 'created_at']
        read_only_fields = ['id', 'file_name', 'created_at']

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, f):
        if f.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError('回执附件不能超过 100MB')
        return f

    def validate(self, attrs):
        if not attrs.get('receipt_date'):
            raise serializers.ValidationError({'receipt_date': '请填写回执日期'})
        return attrs

    def create(self, validated_data):
        uploaded = validated_data.get('file')
        if uploaded is not None:
            validated_data['file_name'] = uploaded.name
        receipt = None
        try:
            with transaction.atomic():
                submission = (MaterialSubmission.objects
                              .select_for_update()
                              .get(pk=validated_data['submission'].pk))
                validated_data['submission'] = submission
                receipt = SubmissionReceipt(**validated_data)
                receipt.save()

                material_ids = list(
                    submission.items.values_list('version__material_id', flat=True))
                if receipt.receipt_type == 'signed':
                    submission.status = 'signed'
                    Material.objects.filter(pk__in=material_ids).update(status='signed')
                else:
                    submission.status = 'returned'
                    Material.objects.filter(pk__in=material_ids).update(status='returned')
                submission.save(update_fields=['status'])
        except Exception:
            if receipt is not None and receipt.file:
                receipt.file.delete(save=False)
            if uploaded is not None:
                uploaded.close()
            raise
        return receipt


class SubmissionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionItem
        fields = ['id', 'version', 'material_name', 'version_no',
                  'file_name', 'copies', 'pages']
        read_only_fields = fields


class MaterialSubmissionSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = SubmissionItemSerializer(many=True, read_only=True)
    receipts = SubmissionReceiptSerializer(many=True, read_only=True)

    class Meta:
        model = MaterialSubmission
        fields = ['id', 'case', 'submitted_to', 'receiver_name', 'method',
                  'method_display', 'submit_date', 'note', 'status',
                  'status_display', 'created_by', 'resubmitted_from',
                  'items', 'receipts', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']


class SubmissionItemWriteSerializer(serializers.Serializer):
    version_id = serializers.IntegerField()
    copies = serializers.IntegerField(min_value=1, default=1)
    pages = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    def validate_version_id(self, value):
        if not MaterialVersion.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'版本 {value} 不存在')
        return value


class SubmissionCreateSerializer(serializers.Serializer):
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    submitted_to = serializers.CharField(max_length=100)
    receiver_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    method = serializers.ChoiceField(
        choices=MaterialSubmission.METHOD_CHOICES, default='window')
    submit_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True)
    created_by = serializers.CharField(max_length=50)
    resubmitted_from = serializers.PrimaryKeyRelatedField(
        queryset=MaterialSubmission.objects.all(), required=False, allow_null=True)
    items = SubmissionItemWriteSerializer(many=True)

    def validate_created_by(self, value):
        if not value.strip():
            raise serializers.ValidationError('请填写提交经办人')
        return value

    def validate(self, attrs):
        items = attrs.get('items') or []
        if not items:
            raise serializers.ValidationError({'items': '提交清单不能为空'})
        version_ids = [it['version_id'] for it in items]
        if len(set(version_ids)) != len(version_ids):
            raise serializers.ValidationError({'items': '同一版本在清单中重复'})

        case = attrs['case']
        versions = (MaterialVersion.objects
                    .select_related('material')
                    .filter(pk__in=version_ids))
        if len(versions) != len(set(version_ids)):
            raise serializers.ValidationError({'items': '存在不存在的版本'})
        for v in versions:
            if v.material.case_id != case.id:
                raise serializers.ValidationError(
                    {'items': f'「{v.material.name} v{v.version_no}」不属于本案'})
            if not v.is_final:
                raise serializers.ValidationError(
                    {'items': f'「{v.material.name} v{v.version_no}」尚未定稿，不能提交'})
            if not v.file:
                raise serializers.ValidationError(
                    {'items': f'「{v.material.name} v{v.version_no}」缺少附件，不能提交'})

        prior = attrs.get('resubmitted_from')
        if prior is not None and prior.case_id != case.id:
            raise serializers.ValidationError(
                {'resubmitted_from': '原提交批次不属于本案'})
        if prior is not None and prior.status != 'returned':
            raise serializers.ValidationError(
                {'resubmitted_from': '仅退回补正的批次可以发起重新提交'})
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        version_ids = [it['version_id'] for it in items_data]
        with transaction.atomic():
            case = Case.objects.select_for_update().get(pk=validated_data['case'].pk)
            versions = {v.id: v for v in
                        MaterialVersion.objects.select_for_update()
                        .select_related('material')
                        .filter(pk__in=version_ids)}

            submission = MaterialSubmission.objects.create(
                case=case,
                submitted_to=validated_data['submitted_to'],
                receiver_name=validated_data.get('receiver_name', ''),
                method=validated_data.get('method', 'window'),
                submit_date=validated_data['submit_date'],
                note=validated_data.get('note', ''),
                created_by=validated_data['created_by'],
                resubmitted_from=validated_data.get('resubmitted_from'),
                status='submitted')

            item_objs = []
            material_ids = set()
            for it in items_data:
                v = versions[it['version_id']]
                material_ids.add(v.material_id)
                item_objs.append(SubmissionItem(
                    submission=submission, version=v,
                    material_name=v.material.name, version_no=v.version_no,
                    file_name=v.file_name, copies=it.get('copies', 1),
                    pages=it.get('pages')))
            SubmissionItem.objects.bulk_create(item_objs)
            # 提交后所用版本即被固定：材料进入已提交，等待签收/退回回执
            Material.objects.filter(pk__in=material_ids).update(status='submitted')
        return submission


# ---------- 材料 ----------

class MaterialSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    versions = MaterialVersionSerializer(many=True, read_only=True)
    final_version_no = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ['id', 'case', 'name', 'category', 'status', 'status_display',
                  'notes', 'created_at', 'versions', 'final_version_no',
                  'latest_submission']
        read_only_fields = ['id', 'status', 'created_at']

    def get_final_version_no(self, obj):
        fv = obj.final_version
        return fv.version_no if fv else None

    def get_latest_submission(self, obj):
        item = (SubmissionItem.objects
                .filter(version__material=obj)
                .select_related('submission')
                .order_by('-submission__submit_date', '-submission__id')
                .first())
        if not item:
            return None
        s = item.submission
        return {
            'submission_id': s.id,
            'submitted_to': s.submitted_to,
            'submit_date': s.submit_date,
            'version_no': item.version_no,
            'status': s.status,
            'status_display': s.get_status_display(),
        }


class MaterialBriefSerializer(serializers.ModelSerializer):
    """案件详情内嵌：带版本概要，避免载荷过大"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    versions = MaterialVersionSerializer(many=True, read_only=True)
    final_version_no = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ['id', 'name', 'category', 'status', 'status_display',
                  'notes', 'created_at', 'versions', 'final_version_no']

    def get_final_version_no(self, obj):
        fv = obj.final_version
        return fv.version_no if fv else None


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
    materials = MaterialBriefSerializer(many=True, read_only=True)
    material_submissions = MaterialSubmissionSerializer(many=True, read_only=True)
    deadlines = DeadlineSerializer(many=True, read_only=True)

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            'description', 'hearings', 'stage_logs', 'materials',
            'material_submissions', 'deadlines']


class CaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'stage', 'cause',
                  'court', 'filed_date', 'amount', 'description']
