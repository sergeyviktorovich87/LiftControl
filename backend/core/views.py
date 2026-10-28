from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import Building, Elevator, Maintenance, Technician, Ticket
from .serializers import BuildingSerializer, ElevatorSerializer, MaintenanceSerializer, TechnicianSerializer, TicketSerializer


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok', 'service': 'LiftControl API'})


@api_view(['GET'])
def dashboard(request):
    today = timezone.localdate()
    return Response({
        'buildings': Building.objects.count(),
        'elevators': Elevator.objects.filter(active=True).count(),
        'technicians': Technician.objects.filter(active=True).count(),
        'open_tickets': Ticket.objects.exclude(status__in=[Ticket.Status.DONE, Ticket.Status.CANCELED]).count(),
        'emergency_tickets': Ticket.objects.exclude(status__in=[Ticket.Status.DONE, Ticket.Status.CANCELED]).filter(priority=Ticket.Priority.EMERGENCY).count(),
        'maintenance_today': Maintenance.objects.filter(planned_date=today).count(),
    })


class BuildingViewSet(ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer


class TechnicianViewSet(ModelViewSet):
    queryset = Technician.objects.all()
    serializer_class = TechnicianSerializer


class ElevatorViewSet(ModelViewSet):
    queryset = Elevator.objects.select_related('building', 'assigned_technician').all()
    serializer_class = ElevatorSerializer


class TicketViewSet(ModelViewSet):
    queryset = Ticket.objects.select_related('elevator__building', 'assigned_to').all()
    serializer_class = TicketSerializer


class MaintenanceViewSet(ModelViewSet):
    queryset = Maintenance.objects.select_related('elevator__building', 'technician').all()
    serializer_class = MaintenanceSerializer
