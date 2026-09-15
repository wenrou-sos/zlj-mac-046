from datetime import date, timedelta

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, SAFE_METHODS
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import (AuditLog, Case, CaseAccess, CaseLawyer, CaseParty, Deadline,
                     Hearing, Lawyer, Material, Party, StageLog, UserProfile)
from .permissions import CaseScopedPermission, IsAdminRole, IsAuthenticatedDRF
from .serializers import (AuditLogSerializer, CaseAccessGrantSerializer,
                          CaseAccessSerializer, CaseDetailSerializer,
                          CaseLawyerSerializer, CaseListSerializer,
                          CasePartySerializer, CaseWriteSerializer,
                          DeadlineSerializer, HearingSerializer,
                          LawyerSerializer, MaterialSerializer, PartySerializer,
                          StageLogSerializer, UserCreateSerializer,
                          UserSerializer)
from .services import (active_access_qs, can_edit_case, is_admin, log_audit,
                       record_lapsed_accesses, visible_case_ids, visible_cases)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

def _me_payload(user):
    data = UserSerializer(user).data
    data['is_admin'] = is_admin(user)
    return data


@api_view(['GET'])
@ensure_csrf_cookie
def me(request):
    if not request.user.is_authenticated:
        return Response({'detail': '未登录'}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(_me_payload(request.user))


@api_view(['POST'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def login(request):
    username = (request.data.get('username') or '').strip()
    password = request.data.get('password') or ''
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        log_audit(user if user and user.is_authenticated else None, 'login_failed',
                  detail=f'登录失败：{username}', request=request)
        return Response({'detail': '用户名或密码错误，或账号已停用'},
                        status=status.HTTP_400_BAD_REQUEST)
    auth_login(request, user)
    log_audit(user, 'login', detail='登录系统', request=request)
    return Response(_me_payload(user))


@api_view(['POST'])
def logout(request):
    if request.user.is_authenticated:
        log_audit(request.user, 'logout', detail='退出登录', request=request)
    auth_logout(request)
    return Response({'detail': '已退出'})


# ---------------------------------------------------------------------------
# 账号管理（管理员）
# ---------------------------------------------------------------------------

class AccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedDRF, IsAdminRole]
    queryset = User.objects.select_related('profile', 'profile__lawyer').all()
    # 账号只做停用/启用，不提供物理删除（保留审计可追溯性）
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        log_audit(self.request.user, 'grant', target_user=user,
                  detail=f"创建账号 {user.username}，"
                         f"角色：{user.profile.get_role_display()}",
                  request=self.request)

    def perform_update(self, serializer):
        old = {
            'role': serializer.instance.profile.role,
            'lawyer_id': serializer.instance.profile.lawyer_id,
            'is_active': serializer.instance.is_active,
        }
        user = serializer.save()
        user.refresh_from_db()
        changes = []
        if old['role'] != user.profile.role:
            changes.append(f'角色变更为「{user.profile.get_role_display()}」')
        if old['lawyer_id'] != user.profile.lawyer_id:
            lawyer = user.profile.lawyer
            changes.append(f"绑定律师档案变更为「{lawyer.name if lawyer else '无'}」")
        if old['is_active'] and not user.is_active:
            changes.append('账号已停用（立即失效）')
            # 立即作废该账号的全部会话
            from django.contrib.sessions.models import Session
            for sess in Session.objects.filter(expire_date__gt=timezone.now()):
                data = sess.get_decoded()
                if str(data.get('_auth_user_id')) == str(user.id):
                    sess.delete()
        elif not old['is_active'] and user.is_active:
            changes.append('账号已启用')
        if changes:
            log_audit(self.request.user,
                      'revoke' if not user.is_active else 'grant',
                      target_user=user, detail='；'.join(changes),
                      request=self.request)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get('password') or ''
        if len(password) < 6:
            raise ValidationError({'password': '密码长度至少 6 位'})
        user.set_password(password)
        user.save(update_fields=['password'])
        log_audit(request.user, 'grant', target_user=user,
                  detail='重置登录密码', request=request)
        return Response({'detail': '密码已重置'})


# ---------------------------------------------------------------------------
# 案件授权（管理员/主办律师）
# ---------------------------------------------------------------------------

class CaseAccessViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CaseAccessSerializer

    def get_queryset(self):
        qs = CaseAccess.objects.select_related(
            'user', 'user__profile', 'user__profile__lawyer', 'case')
        if not is_admin(self.request.user):
            # 可查看：自己的授权，以及自己担任主办的案件下的全部授权
            lead_cases = active_access_qs(self.request.user).filter(
                role='lead').values('case_id')
            qs = qs.filter(Q(user=self.request.user) | Q(case_id__in=lead_cases))
        p = self.request.query_params
        if p.get('case'):
            qs = qs.filter(case_id=p['case'])
        if p.get('user'):
            qs = qs.filter(user_id=p['user'])
        if p.get('valid') == 'true':
            now = timezone.now()
            qs = qs.filter(revoked=False).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        return qs

    def _manageable_case(self, request, case):
        """管理员或本案主办可管理授权"""
        if is_admin(request.user):
            return case
        if active_access_qs(request.user).filter(case=case, role='lead').exists():
            return case
        raise PermissionDenied('仅管理员或本案主办律师可管理授权')

    @action(detail=False, methods=['get'], url_path='grantable-users')
    def grantable_users(self, request):
        """可授权账号的精简列表（管理员与案件主办均可调用，不暴露账号管理信息）"""
        case_id = request.query_params.get('case')
        if case_id:
            case = Case.objects.filter(pk=case_id).first()
            if case is None:
                raise ValidationError({'case': '案件不存在'})
            self._manageable_case(request, case)
        elif not is_admin(request.user):
            # 非管理员必须指定自己主办的案件，避免全量账号信息外泄
            raise PermissionDenied('请指定案件')
        users = (User.objects.filter(is_active=True)
                 .exclude(is_superuser=True)
                 .select_related('profile', 'profile__lawyer'))
        data = [{
            'id': u.id,
            'username': u.username,
            'display_name': (u.profile.lawyer.name if u.profile.lawyer_id
                             else u.last_name) or u.username,
            'role': u.profile.role,
            'role_display': u.profile.get_role_display(),
        } for u in users if hasattr(u, 'profile') and u.profile.role != 'admin']
        return Response(data)

    @action(detail=False, methods=['post'])
    def grant(self, request):
        """按案件授权 / 限时借阅"""
        serializer = CaseAccessGrantSerializer(data=request.data,
                                               context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        case = data['case']
        self._manageable_case(request, case)
        target = User.objects.select_related('profile').get(pk=data['user_id'])
        if is_admin(target):
            raise ValidationError({'user_id': '管理员默认可见全部案件，无需授权'})

        expires_at = data.get('expires_at')
        acc = CaseAccess.objects.filter(case=case, user=target).first()
        verb = '新增授权'
        if acc:
            acc.role = data['role']
            acc.source = 'grant'
            acc.expires_at = expires_at
            acc.revoked = False
            acc.revoked_at = None
            acc.save()
            verb = '调整授权'
        else:
            acc = CaseAccess.objects.create(
                case=case, user=target, role=data['role'], source='grant',
                expires_at=expires_at)
        scope = f'{acc.get_role_display()}权限'
        if expires_at:
            scope += f'（限时借阅至 {timezone.localtime(expires_at):%Y-%m-%d %H:%M}）'
        log_audit(request.user, 'grant', target_user=target, case=case, access=acc,
                  detail=f'{verb}：{target.username} 获得案件「{case.title}」{scope}',
                  request=request)
        return Response(CaseAccessSerializer(acc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """立即撤权"""
        acc = get_object_or_404(CaseAccess, pk=pk)
        self._manageable_case(request, acc.case)
        if acc.source == 'team':
            raise ValidationError('团队授权随承办关系自动生成，'
                                  '请在案件详情中移除该承办律师以撤权')
        if not acc.revoked:
            acc.revoked = True
            acc.revoked_at = timezone.now()
            acc.save(update_fields=['revoked', 'revoked_at'])
        log_audit(request.user, 'revoke', target_user=acc.user, case=acc.case,
                  access=acc,
                  detail=f"立即撤销 {acc.user.username} 对案件「{acc.case.title}」的访问权限",
                  request=request)
        return Response(CaseAccessSerializer(acc).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """恢复已撤销的授权"""
        acc = get_object_or_404(CaseAccess, pk=pk)
        self._manageable_case(request, acc.case)
        if acc.revoked:
            acc.revoked = False
            acc.revoked_at = None
            acc.save(update_fields=['revoked', 'revoked_at'])
        log_audit(request.user, 'grant', target_user=acc.user, case=acc.case,
                  access=acc,
                  detail=f"恢复 {acc.user.username} 对案件「{acc.case.title}」的访问权限",
                  request=request)
        return Response(CaseAccessSerializer(acc).data)


# ---------------------------------------------------------------------------
# 审计日志（管理员）
# ---------------------------------------------------------------------------

class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticatedDRF, IsAdminRole]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        qs = AuditLog.objects.select_related('actor', 'target_user', 'case')
        p = self.request.query_params
        for key in ('action', 'actor', 'target_user', 'case'):
            if p.get(key):
                qs = qs.filter(**{key: p[key]})
        if p.get('date_from'):
            qs = qs.filter(created_at__date__gte=p['date_from'])
        if p.get('date_to'):
            qs = qs.filter(created_at__date__lte=p['date_to'])
        return qs


# ---------------------------------------------------------------------------
# 基础档案
# ---------------------------------------------------------------------------

class LawyerViewSet(viewsets.ModelViewSet):
    serializer_class = LawyerSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticatedDRF()]
        return [IsAuthenticatedDRF(), IsAdminRole()]

    def get_queryset(self):
        qs = Lawyer.objects.all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(bar_number__icontains=search))
        return qs


class PartyViewSet(viewsets.ModelViewSet):
    serializer_class = PartySerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticatedDRF()]
        if self.request.method == 'POST':
            # 办案律师建案时可新建当事人档案；删除/修改档案仅管理员
            return [IsAuthenticatedDRF()]
        return [IsAuthenticatedDRF(), IsAdminRole()]

    def get_queryset(self):
        qs = Party.objects.all()
        ids = visible_case_ids(self.request.user)
        if ids is not None:
            # 仅能看到：参与了自己可见案件的当事人，以及本人建档但尚未挂到案件的当事人
            qs = qs.filter(Q(cases__in=ids) | Q(created_by=self.request.user)).distinct()
        search = self.request.query_params.get('search', '').strip()
        ptype = self.request.query_params.get('party_type', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(id_number__icontains=search))
        if ptype:
            qs = qs.filter(party_type=ptype)
        return qs

    def create(self, request, *args, **kwargs):
        if not is_admin(request.user) and \
                request.user.profile.role == 'reader':
            raise PermissionDenied('只读助理不能新建当事人档案')
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ---------------------------------------------------------------------------
# 案件
# ---------------------------------------------------------------------------

class CaseViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        return [IsAuthenticatedDRF()]

    def get_queryset(self):
        qs = visible_cases(self.request.user).prefetch_related(
            'caselawyer_set__lawyer', 'caseparty_set__party', 'deadlines')
        p = self.request.query_params
        if p.get('stage'):
            qs = qs.filter(stage=p['stage'])
        if p.get('case_type'):
            qs = qs.filter(case_type=p['case_type'])
        search = p.get('search', '').strip()
        if search:
            qs = qs.filter(Q(case_number__icontains=search) | Q(title__icontains=search))
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CaseDetailSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return CaseWriteSerializer
        return CaseListSerializer

    def _deny_if_no_edit(self, case):
        if not can_edit_case(self.request.user, case):
            raise PermissionDenied('您对该案件只有只读权限')

    def create(self, request, *args, **kwargs):
        if not is_admin(request.user) and request.user.profile.role == 'reader':
            raise PermissionDenied('只读助理不能新建案件')
        # 复用 perform_create 后，以列表序列化器返回（含 my_access），保证前端立即可见
        response = super().create(request, *args, **kwargs)
        case = Case.objects.filter(pk=response.data['id']).first()
        if case is not None:
            response.data = CaseListSerializer(case, context={'request': request}).data
            response.status_code = status.HTTP_201_CREATED
        return response

    def perform_create(self, serializer):
        case = serializer.save()
        user = self.request.user
        if not is_admin(user):
            # 登记案件即加入自己的办案团队，自动获得团队授权
            profile = user.profile
            if profile.lawyer_id:
                CaseLawyer.objects.get_or_create(
                    case=case, lawyer=profile.lawyer, defaults={'role': 'lead'})
            else:
                CaseAccess.objects.get_or_create(
                    case=case, user=user,
                    defaults={'role': 'lead', 'source': 'grant'})
        return case

    def update(self, request, *args, **kwargs):
        self._deny_if_no_edit(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._deny_if_no_edit(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied('仅管理员可删除案件')
        case = self.get_object()
        log_audit(request.user, 'case_delete', case=case,
                  detail=f'删除案件：{case.case_number} {case.title}',
                  request=request)
        return super().destroy(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # 直接访问详情同样遵循可见范围：不可见统一 404，不泄露案件是否存在
        case = Case.objects.filter(pk=kwargs['pk']).first()
        if case is None:
            return Response({'detail': '案件不存在'}, status=status.HTTP_404_NOT_FOUND)
        if not self.get_queryset().filter(pk=case.pk).exists():
            log_audit(request.user, 'case_view', case=case,
                      detail=f'越权访问案件详情被拦截：{case.case_number} {case.title}',
                      request=request)
            return Response({'detail': '案件不存在或您无权查看'},
                            status=status.HTTP_404_NOT_FOUND)
        acc = active_access_qs(request.user).filter(case=case).first()
        # 管理员查看、限时借阅/手动授权访问属敏感访问，留痕；团队日常查看不记录
        if is_admin(request.user) or (acc and acc.source == 'grant'):
            log_audit(request.user, 'case_view', case=case, access=acc,
                      detail=('管理员查看案件详情' if is_admin(request.user)
                              else f'借阅账号查看案件详情（{acc.get_role_display()}）'),
                      request=request)
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='conflict-check',
            permission_classes=[IsAuthenticatedDRF])
    def conflict_check(self, request, pk=None):
        """向本案添加当事人前的利益冲突预检（仅披露可见案件的冲突）"""
        case = self.get_object()
        party = get_object_or_404(Party, pk=request.data.get('party_id'))
        is_client = bool(request.data.get('is_client'))

        visible_ids = visible_case_ids(request.user)

        conflicts = []
        existing = CaseParty.objects.filter(case=case, party=party).first()
        if existing:
            conflicts.append({
                'level': 'high',
                'message': f'该当事人已是本案{existing.get_role_display()}，请勿重复添加',
            })

        other_qs = (CaseParty.objects.filter(party=party).exclude(case=case)
                    .select_related('case'))
        if visible_ids is not None:
            other_qs = other_qs.filter(case_id__in=visible_ids)
        for cp in other_qs:
            title = cp.case.title
            if cp.is_client and cp.case.stage != 'closed' and not is_client:
                conflicts.append({
                    'level': 'high',
                    'message': f'该当事人是本所在办案件「{title}」的委托客户，'
                               f'本案拟列为对方当事人，构成直接利益冲突',
                })
            elif cp.is_client and is_client:
                conflicts.append({
                    'level': 'low',
                    'message': f'该当事人已是本所客户（案件「{title}」），请注意信息隔离',
                })
            elif not cp.is_client and is_client and cp.case.stage != 'closed':
                conflicts.append({
                    'level': 'medium',
                    'message': f'该当事人是本所在办案件「{title}」的对方当事人，'
                               f'接受其委托前须进行冲突审查并取得相关方同意',
                })

        has_high = any(c['level'] == 'high' for c in conflicts)
        return Response({'has_conflict': has_high, 'conflicts': conflicts})


# ---------------------------------------------------------------------------
# 案件关联记录：统一按案件可见范围过滤、按案件编辑权限限写
# ---------------------------------------------------------------------------

class CaseScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedDRF, CaseScopedPermission]
    case_param = 'case'

    def scope_queryset(self, qs):
        return qs

    def get_queryset(self):
        qs = self.scope_queryset(self.queryset)
        ids = visible_case_ids(self.request.user)
        if ids is not None:
            qs = qs.filter(case_id__in=ids)
        case_id = self.request.query_params.get(self.case_param)
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def create(self, request, *args, **kwargs):
        case_id = request.data.get('case')
        case = visible_cases(request.user).filter(pk=case_id).first()
        if case is None:
            raise PermissionDenied('案件不存在或您无权操作')
        if not can_edit_case(request.user, case):
            raise PermissionDenied('您对该案件只有只读权限')
        return super().create(request, *args, **kwargs)


class CasePartyViewSet(CaseScopedModelViewSet):
    serializer_class = CasePartySerializer
    queryset = CaseParty.objects.select_related('party', 'case')


class CaseLawyerViewSet(CaseScopedModelViewSet):
    serializer_class = CaseLawyerSerializer
    queryset = CaseLawyer.objects.select_related('lawyer', 'case')

    def perform_destroy(self, instance):
        target = UserProfile.objects.filter(
            lawyer=instance.lawyer).select_related('user').first()
        super().perform_destroy(instance)  # 信号会同步撤销团队授权
        if target:
            log_audit(self.request.user, 'revoke', target_user=target.user,
                      case=instance.case,
                      detail=f"将 {instance.lawyer.name} 移出案件「{instance.case.title}」"
                             f"承办团队，其访问权限同步撤销",
                      request=self.request)


class HearingViewSet(CaseScopedModelViewSet):
    serializer_class = HearingSerializer
    queryset = Hearing.objects.select_related('case')


class StageLogViewSet(CaseScopedModelViewSet):
    serializer_class = StageLogSerializer
    queryset = StageLog.objects.select_related('case')


class MaterialViewSet(CaseScopedModelViewSet):
    serializer_class = MaterialSerializer
    queryset = Material.objects.select_related('case')


class DeadlineViewSet(CaseScopedModelViewSet):
    serializer_class = DeadlineSerializer
    queryset = Deadline.objects.select_related('case')

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('done') in ('true', 'false'):
            qs = qs.filter(is_done=(p['done'] == 'true'))
        if p.get('upcoming'):
            days = int(p.get('days', 30))
            qs = qs.filter(is_done=False,
                           due_date__lte=date.today() + timedelta(days=days))
        return qs


# ---------------------------------------------------------------------------
# 工作台
# ---------------------------------------------------------------------------

@api_view(['GET'])
def dashboard(request):
    """工作台统计：全部数据按当前账号可见案件范围计算"""
    record_lapsed_accesses()
    today = date.today()
    soon = today + timedelta(days=30)
    cases = visible_cases(request.user)
    ids = visible_case_ids(request.user)

    stage_stats = []
    counts = {row['stage']: row['n'] for row in cases.values('stage').annotate(n=Count('id'))}
    for key, label in Case.STAGE_CHOICES:
        stage_stats.append({'stage': key, 'stage_display': label,
                            'count': counts.get(key, 0)})

    hearings = Hearing.objects.all()
    deadlines_qs = Deadline.objects.all()
    if ids is not None:
        hearings = hearings.filter(case_id__in=ids)
        deadlines_qs = deadlines_qs.filter(case_id__in=ids)

    hearings = hearings.filter(
        hearing_time__date__gte=today).select_related('case').order_by('hearing_time')[:10]
    deadlines = deadlines_qs.filter(
        is_done=False, due_date__lte=soon).select_related('case').order_by('due_date')[:20]
    overdue = deadlines_qs.filter(is_done=False, due_date__lt=today).count()

    party_qs = Party.objects.filter(cases__in=cases).distinct()
    lawyer_qs = Lawyer.objects.filter(cases__in=cases).distinct()

    return Response({
        'case_total': cases.count(),
        'case_active': cases.exclude(stage='closed').count(),
        'party_total': party_qs.count(),
        'lawyer_total': lawyer_qs.count(),
        'deadline_overdue': overdue,
        'stage_stats': stage_stats,
        'hearings_upcoming': HearingSerializer(hearings, many=True).data,
        'deadlines_upcoming': DeadlineSerializer(deadlines, many=True).data,
    })


# ---------------------------------------------------------------------------
# 利益冲突检查
# ---------------------------------------------------------------------------

def _party_involvements(party, visible_ids):
    """汇总当事人在【可见】案件中的涉诉情况"""
    qs = (CaseParty.objects.filter(party=party)
          .select_related('case').order_by('-case__filed_date'))
    if visible_ids is not None:
        qs = qs.filter(case_id__in=visible_ids)
    items = []
    for cp in qs:
        items.append({
            'case_id': cp.case.id,
            'case_number': cp.case.case_number,
            'case_title': cp.case.title,
            'stage': cp.case.stage,
            'stage_display': cp.case.get_stage_display(),
            'role': cp.role,
            'role_display': cp.get_role_display(),
            'is_client': cp.is_client,
        })
    return items


@api_view(['GET'])
def conflict_check(request):
    """利益冲突检查：仅检索当前账号可见案件范围内的涉诉记录"""
    name = request.query_params.get('name', '').strip()
    id_number = request.query_params.get('id_number', '').strip()
    if not name and not id_number:
        return Response({'detail': '请提供姓名/名称或证件号'}, status=status.HTTP_400_BAD_REQUEST)

    ids = visible_case_ids(request.user)
    base = Party.objects.all()
    if ids is not None:
        base = base.filter(cases__in=ids).distinct()

    q = Q()
    if name:
        q |= Q(name__icontains=name)
    if id_number:
        q |= Q(id_number=id_number)
    parties = base.filter(q).distinct()

    results = []
    for party in parties:
        involvements = _party_involvements(party, ids)
        if not involvements:
            # 无任何可见涉案信息，不暴露该当事人的存在
            continue
        warnings = []
        for inv in involvements:
            if inv['is_client'] and inv['stage'] != 'closed':
                warnings.append(f"系本所在办案件「{inv['case_title']}」的委托客户，"
                                f"代理与其利益相对方构成直接利益冲突")
            elif not inv['is_client']:
                warnings.append(f"在案件「{inv['case_title']}」中为对方当事人"
                                f"（{inv['stage_display']}）")
        if any(w.startswith('系本所') for w in warnings):
            risk = 'high'
        elif warnings:
            risk = 'medium'
        else:
            risk = 'low'
        results.append({
            'party': PartySerializer(party, context={'request': request}).data,
            'involvements': involvements,
            'warnings': warnings,
            'risk': risk,
        })

    log_audit(request.user, 'conflict_check',
              detail=f'利益冲突检索：{name or id_number}，命中 {len(results)} 个当事人',
              request=request)

    return Response({'count': len(results), 'results': results})
