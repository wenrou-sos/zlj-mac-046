from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('cases.urls')),
    # SPA 前端入口（frontend/dist/index.html），同时确保下发 csrftoken Cookie
    re_path(r'^(?!api/|admin/|static/).*$',
            ensure_csrf_cookie(TemplateView.as_view(template_name='index.html'))),
]
