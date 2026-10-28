from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import BuildingViewSet, ElevatorViewSet, MaintenanceViewSet, TechnicianViewSet, TicketViewSet, dashboard, health

router = DefaultRouter()
router.register('buildings', BuildingViewSet)
router.register('elevators', ElevatorViewSet)
router.register('technicians', TechnicianViewSet)
router.register('tickets', TicketViewSet)
router.register('maintenance', MaintenanceViewSet)

urlpatterns = [
    path('health/', health),
    path('dashboard/', dashboard),
    path('', include(router.urls)),
]
