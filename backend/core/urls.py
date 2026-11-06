from django.urls import include,path
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
for name,view in [('buildings',views.BuildingViewSet),('elevators',views.ElevatorViewSet),('technicians',views.TechnicianViewSet),('tickets',views.TicketViewSet),('maintenance',views.MaintenanceViewSet),('duty',views.DutyViewSet),('parts',views.PartViewSet),('chat',views.ChatViewSet),('documents',views.DocumentViewSet)]:
    router.register(name,view)
urlpatterns = [path('health/',views.health),path('me/',views.me),path('logout/',views.sign_out),path('dashboard/',views.dashboard),path('audit/',views.audit_events),path('',include(router.urls))]
