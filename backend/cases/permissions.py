from rest_framework.permissions import SAFE_METHODS, BasePermission

from .services import can_edit_case, is_admin


class IsAuthenticatedDRF(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


class CaseScopedPermission(BasePermission):
    """读：走 queryset 的可见范围过滤；写：需对目标案件具备编辑权限

    create/无对象的写操作由 viewset 自行根据请求体中的 case 校验。
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        case = getattr(obj, 'case', obj)
        return can_edit_case(request.user, case)
