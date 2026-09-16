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
router.register('fee-agreements', views.FeeAgreementViewSet, basename='fee-agreement')
router.register('case-rates', views.CaseRateViewSet, basename='case-rate')
router.register('time-entries', views.TimeEntryViewSet, basename='time-entry')
router.register('expenses', views.ExpenseViewSet, basename='expense')
router.register('bills', views.BillViewSet, basename='bill')
router.register('payments', views.PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('conflict-check/', views.conflict_check, name='conflict-check'),
    path('auth/me/', views.auth_me, name='auth-me'),
    path('auth/login/', views.auth_login, name='auth-login'),
    path('auth/logout/', views.auth_logout, name='auth-logout'),
]
