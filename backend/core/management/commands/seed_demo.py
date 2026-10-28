from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Building, Elevator, Maintenance, Technician, Ticket


class Command(BaseCommand):
    help = 'Создаёт демонстрационные данные LiftControl'

    def handle(self, *args, **options):
        tech1, _ = Technician.objects.get_or_create(full_name='Иван Петров', defaults={'role': Technician.Role.ADJUSTER, 'phone': '+7 900 000-00-01'})
        tech2, _ = Technician.objects.get_or_create(full_name='Алексей Смирнов', defaults={'role': Technician.Role.MECHANIC, 'phone': '+7 900 000-00-02'})
        tech3, _ = Technician.objects.get_or_create(full_name='Сергей Орлов', defaults={'role': Technician.Role.MECHANIC, 'phone': '+7 900 000-00-03'})

        b1, _ = Building.objects.get_or_create(address='ул. Ленина, 120', defaults={'name': 'ЖК Север', 'management_company': 'УК Демонстрация'})
        b2, _ = Building.objects.get_or_create(address='ул. Калинина, 15', defaults={'name': 'Бизнес-центр', 'management_company': 'ООО Управление'})
        b3, _ = Building.objects.get_or_create(address='ул. Горького, 88', defaults={'name': 'Жилой дом', 'management_company': 'ТСЖ Горького'})

        e1, _ = Elevator.objects.get_or_create(factory_number='LC-0001', defaults={'building': b1, 'entrance': '1', 'manufacturer': 'МЭЛ', 'model': 'ПП-1011', 'floors': 16, 'capacity_kg': 1000, 'assigned_technician': tech1})
        e2, _ = Elevator.objects.get_or_create(factory_number='LC-0002', defaults={'building': b1, 'entrance': '2', 'manufacturer': 'МЭЛ', 'model': 'ПП-1011', 'floors': 16, 'capacity_kg': 1000, 'assigned_technician': tech2})
        e3, _ = Elevator.objects.get_or_create(factory_number='LC-0003', defaults={'building': b2, 'entrance': '1', 'manufacturer': 'SJEС', 'model': 'Monarch/NICE3000', 'floors': 12, 'capacity_kg': 1000, 'assigned_technician': tech1})
        e4, _ = Elevator.objects.get_or_create(factory_number='LC-0004', defaults={'building': b3, 'entrance': '1', 'manufacturer': 'ЩЛЗ', 'model': 'УКЛ', 'floors': 9, 'capacity_kg': 630, 'assigned_technician': tech3})

        if not Ticket.objects.exists():
            Ticket.objects.create(elevator=e1, title='Не закрываются двери', description='Повторное открытие после команды закрытия', priority=Ticket.Priority.HIGH, status=Ticket.Status.IN_PROGRESS, assigned_to=tech1)
            Ticket.objects.create(elevator=e2, title='Не работает кнопка вызова', priority=Ticket.Priority.NORMAL, status=Ticket.Status.NEW)
            Ticket.objects.create(elevator=e3, title='Пассажиры застряли в кабине', priority=Ticket.Priority.EMERGENCY, status=Ticket.Status.ASSIGNED, assigned_to=tech2)
            Ticket.objects.create(elevator=e4, title='Шум при движении', priority=Ticket.Priority.NORMAL, status=Ticket.Status.NEW, assigned_to=tech3)

        today = timezone.localdate()
        if not Maintenance.objects.exists():
            Maintenance.objects.create(elevator=e1, technician=tech1, kind=Maintenance.Kind.TO1, planned_date=today)
            Maintenance.objects.create(elevator=e2, technician=tech2, kind=Maintenance.Kind.TO1, planned_date=today)
            Maintenance.objects.create(elevator=e3, technician=tech1, kind=Maintenance.Kind.TO1, planned_date=today + timedelta(days=1))
            Maintenance.objects.create(elevator=e4, technician=tech3, kind=Maintenance.Kind.TO1, planned_date=today + timedelta(days=2))

        self.stdout.write(self.style.SUCCESS('Демо-данные LiftControl созданы.'))
