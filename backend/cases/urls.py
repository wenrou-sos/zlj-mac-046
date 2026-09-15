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
router.register('deadline-events', views.DeadlineEventViewSet, basename='deadline-event')
router.register('deadline-rules', views.DeadlineRuleViewSet, basename='deadline-rule')
router.register('holidays', views.HolidayViewSet, basename='holiday')
router.register('reminders', views.ReminderViewSet, basename='reminder')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('conflict-check/', views.conflict_check, name='conflict-check'),
]
