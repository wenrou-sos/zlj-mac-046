"""DRF 会话认证：未登录访问受保护接口返回 401（便于前端跳转登录），
写请求仍强制 Django CSRF 校验。"""
from rest_framework.authentication import (BasicAuthentication,
                                           SessionAuthentication)


class SessionAuth401(SessionAuthentication):
    def authenticate_header(self, request):
        return 'Session'


class BasicAuth401(BasicAuthentication):
    def authenticate_header(self, request):
        return 'Basic'
