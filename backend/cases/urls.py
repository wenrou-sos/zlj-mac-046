from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register('lawyers', views.LawyerViewSet, basename='lawyer')
router.register('parties', views.PartyViewSet, basename='party')
router.register('cases', views.CaseViewSet, basename='case')
router.register('case-parties', views.CasePartyViewSet, basename='case-party')
router.register('case-lawyers', views.CaseLawyerViewSet, basename='case-lawyer')
router.register('hearings', views.HearingViewSet, basename='hearing')
router.register('stage-logs', views.StageLogViewSet, basename='stage-log')
router.register('materials', views.MaterialViewSet, basename='material')
router.register('deadlines', views.DeadlineViewSet, basename='deadline')
router.register('access', views.CaseAccessViewSet, basename='access')
router.register('accounts', views.AccountViewSet, basename='account')
router.register('audit-logs', views.AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/me/', views.me),
    path('auth/login/', views.login),
    path('auth/logout/', views.logout),
    path('dashboard/', views.dashboard),
    path('conflict-check/', views.conflict_check),
]
