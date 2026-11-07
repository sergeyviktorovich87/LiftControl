from django.urls import include,path
from rest_framework.routers import DefaultRouter
from . import views, organizations
router = DefaultRouter()
for name,view in [('buildings',views.BuildingViewSet),('elevators',views.ElevatorViewSet),('technicians',views.TechnicianViewSet),('tickets',views.TicketViewSet),('maintenance',views.MaintenanceViewSet),('duty',views.DutyViewSet),('duty-swaps',views.DutySwapViewSet),('parts',views.PartViewSet),('chat',views.ChatViewSet),('documents',views.DocumentViewSet)]:
    router.register(name,view)
urlpatterns = [path('organizations/',organizations.organizations),path('organizations/switch/',organizations.switch_organization),path('organizations/join/',organizations.join_organization),path('organizations/invites/',organizations.organization_invites),path('organizations/invites/<int:invite_id>/revoke/',organizations.revoke_invite),path('organizations/members/',organizations.organization_members),path('organizations/members/create/',organizations.create_employee_account),path('organizations/members/<int:member_id>/',organizations.update_member),path('push/public-key/',views.push_public_key),path('push/subscription/',views.push_subscription),path('health/',views.health),path('me/',views.me),path('logout/',views.sign_out),path('dashboard/',views.dashboard),path('audit/',views.audit_events),path('',include(router.urls))]

