from datetime import date

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (AuditLog, Case, CaseAccess, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog, UserProfile)
from .services import is_admin, my_access_info, visible_case_ids


class UserProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    lawyer_name = serializers.CharField(source='lawyer.name', read_only=True, default=None)

    class Meta:
        model = UserProfile
        fields = ['role', 'role_display', 'lawyer', 'lawyer_name']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()
    display_name = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'last_name', 'display_name', 'is_active', 'last_login',
                  'date_joined', 'is_admin', 'profile']

    def get_is_admin(self, obj):
        return obj.is_superuser or (hasattr(obj, 'profile')
                                    and obj.profile.role == 'admin')

    def get_display_name(self, obj):
        lawyer = getattr(obj.profile, 'lawyer', None)
        return (lawyer.name if lawyer else obj.last_name) or obj.username

    def update(self, instance, validated_attrs):
        profile_attrs = validated_attrs.pop('profile', {})
        instance.is_active = validated_attrs.get('is_active', instance.is_active)
        instance.last_name = validated_attrs.get('last_name', instance.last_name)
        instance.save(update_fields=['last_name', 'is_active'])
        profile = instance.profile
        for key, value in profile_attrs.items():
            setattr(profile, key, value)
        if profile_attrs:
            profile.save()
        return instance


class UserCreateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserProfile.ROLE_CHOICES, write_only=True)
    lawyer = serializers.PrimaryKeyRelatedField(
        queryset=Lawyer.objects.all(), allow_null=True, required=False, write_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'last_name', 'display_name',
                  'role', 'lawyer', 'is_active']
        extra_kwargs = {'password': {'write_only': True},
                        'last_name': {'write_only': True, 'required': False,
                                      'allow_blank': True}}

    def get_display_name(self, obj):
        lawyer = getattr(obj.profile, 'lawyer', None)
        return (lawyer.name if lawyer else obj.last_name) or obj.username

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('登录名已存在')
        return value

    def create(self, validated_attrs):
        role = validated_attrs.pop('role')
        lawyer = validated_attrs.pop('lawyer', None)
        password = validated_attrs.pop('password')
        user = User.objects.create_user(password=password, **validated_attrs)
        profile = user.profile
        profile.role = role
        profile.lawyer = lawyer
        profile.save()
        return user


class CaseAccessSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    display_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = CaseAccess
        fields = ['id', 'case', 'user', 'username', 'display_name', 'role',
                  'role_display', 'source', 'source_display', 'granted_at',
                  'expires_at', 'revoked', 'revoked_at', 'is_valid']

    def get_display_name(self, obj):
        lawyer = getattr(obj.user.profile, 'lawyer', None)
        return (lawyer.name if lawyer else obj.user.last_name) or obj.user.username


class CaseAccessGrantSerializer(serializers.Serializer):
    case = serializers.PrimaryKeyRelatedField(queryset=Case.objects.all())
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=[('lead', '主办律师'),
                                            ('assist', '协办律师'),
                                            ('reader', '只读')])
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError('账号不存在')
        return value


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    target_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    case_number = serializers.CharField(source='case.case_number', read_only=True,
                                        default=None)

    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'action_display',
                  'target_user', 'target_name', 'case', 'case_number',
                  'detail', 'ip', 'created_at']

    def _name(self, user):
        if not user:
            return None
        lawyer = getattr(user.profile, 'lawyer', None)
        return (lawyer.name if lawyer else user.last_name) or user.username

    def get_actor_name(self, obj):
        return self._name(obj.actor)

    def get_target_name(self, obj):
        return self._name(obj.target_user)


class LawyerSerializer(serializers.ModelSerializer):
    title_display = serializers.CharField(source='get_title_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Lawyer
        fields = '__all__'

    def get_case_count(self, obj):
        ids = visible_case_ids(self.context['request'].user)
        qs = obj.cases.exclude(stage='closed')
        if ids is not None:
            qs = qs.filter(id__in=ids)
        return qs.count()


class PartySerializer(serializers.ModelSerializer):
    party_type_display = serializers.CharField(source='get_party_type_display', read_only=True)
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = '__all__'

    def get_case_count(self, obj):
        ids = visible_case_ids(self.context['request'].user)
        qs = obj.cases.all()
        if ids is not None:
            qs = qs.filter(id__in=ids)
        return qs.count()


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
    my_access = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ['id', 'case_number', 'title', 'case_type', 'case_type_display',
                  'stage', 'stage_display', 'cause', 'court', 'filed_date',
                  'amount', 'case_lawyers', 'case_parties',
                  'pending_deadline_count', 'my_access', 'created_at']

    def get_pending_deadline_count(self, obj):
        return obj.deadlines.filter(is_done=False).count()

    def get_my_access(self, obj):
        return my_access_info(self.context['request'].user, obj)


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
