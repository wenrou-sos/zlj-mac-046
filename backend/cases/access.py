"""当前操作律师身份解析。

系统不使用 Django 登录体系，改由前端在页头选择"当前律师"，
并通过 ``X-Lawyer-Id`` 请求头携带；所有冲突复核相关写操作都必须
有明确身份，用于申请人 / 复核人隔离与全程留痕。
"""
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Lawyer

LAWYER_HEADER = 'HTTP_X_LAWYER_ID'


def current_lawyer(request, required=True):
    raw = (request.META.get(LAWYER_HEADER) or '').strip()
    if not raw:
        if required:
            raise ValidationCodeError('请先在页面右上角选择当前操作律师')
        return None
    try:
        lawyer = Lawyer.objects.get(pk=int(raw))
    except (ValueError, Lawyer.DoesNotExist):
        if required:
            raise ValidationCodeError('当前律师身份无效，请重新选择')
        return None
    return lawyer


class ValidationCodeError(ValidationError):
    """以 detail 返回的业务校验错误（前端拦截器可直接展示）。"""
    status_code = 400

    def __init__(self, detail):
        super().__init__({'detail': detail})


def require_reviewer(review, lawyer):
    """只有被指定的复核人本人可以审批；申请人不能审批自己的申请。"""
    if lawyer is None:
        raise ValidationCodeError('请先选择当前操作律师')
    if review.applicant_id == lawyer.id:
        raise PermissionDenied('申请人不能审批自己提交的冲突复核申请')
    if review.reviewer_id != lawyer.id:
        raise PermissionDenied('只有该复核单的指定复核人可以作出审批决定')
