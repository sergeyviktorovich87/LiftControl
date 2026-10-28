from rest_framework import serializers
from .models import Building, Elevator, Maintenance, Technician, Ticket


class BuildingSerializer(serializers.ModelSerializer):
    elevators_count = serializers.IntegerField(source='elevators.count', read_only=True)

    class Meta:
        model = Building
        fields = '__all__'


class TechnicianSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = Technician
        fields = '__all__'


class ElevatorSerializer(serializers.ModelSerializer):
    address = serializers.CharField(source='building.address', read_only=True)
    building_name = serializers.CharField(source='building.name', read_only=True)
    technician_name = serializers.CharField(source='assigned_technician.full_name', read_only=True)
    elevator_type_display = serializers.CharField(source='get_elevator_type_display', read_only=True)

    class Meta:
        model = Elevator
        fields = '__all__'


class TicketSerializer(serializers.ModelSerializer):
    elevator_factory_number = serializers.CharField(source='elevator.factory_number', read_only=True)
    address = serializers.CharField(source='elevator.building.address', read_only=True)
    technician_name = serializers.CharField(source='assigned_to.full_name', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Ticket
        fields = '__all__'


class MaintenanceSerializer(serializers.ModelSerializer):
    elevator_factory_number = serializers.CharField(source='elevator.factory_number', read_only=True)
    address = serializers.CharField(source='elevator.building.address', read_only=True)
    technician_name = serializers.CharField(source='technician.full_name', read_only=True)
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = Maintenance
        fields = '__all__'
