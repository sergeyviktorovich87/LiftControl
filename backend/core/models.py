from django.db import models


class Building(models.Model):
    name = models.CharField('Объект', max_length=200)
    address = models.CharField('Адрес', max_length=300, db_index=True)
    management_company = models.CharField('Управляющая организация', max_length=200, blank=True)
    contact_name = models.CharField('Контактное лицо', max_length=150, blank=True)
    contact_phone = models.CharField('Телефон', max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['address']
        verbose_name = 'Объект'
        verbose_name_plural = 'Объекты'

    def __str__(self):
        return f'{self.address} — {self.name}'


class Technician(models.Model):
    class Role(models.TextChoices):
        MECHANIC = 'MECHANIC', 'Механик'
        ADJUSTER = 'ADJUSTER', 'Наладчик'
        DISPATCHER = 'DISPATCHER', 'Диспетчер'
        ENGINEER = 'ENGINEER', 'Инженер'

    full_name = models.CharField('ФИО', max_length=200)
    phone = models.CharField('Телефон', max_length=50, blank=True)
    role = models.CharField('Роль', max_length=20, choices=Role.choices, default=Role.MECHANIC)
    active = models.BooleanField('Активен', default=True)
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'

    def __str__(self):
        return self.full_name


class Elevator(models.Model):
    class ElevatorType(models.TextChoices):
        PASSENGER = 'PASSENGER', 'Пассажирский'
        FREIGHT = 'FREIGHT', 'Грузовой'
        HOSPITAL = 'HOSPITAL', 'Больничный'
        SERVICE = 'SERVICE', 'Малый грузовой'

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='elevators')
    factory_number = models.CharField('Заводской номер', max_length=100, unique=True)
    model = models.CharField('Модель', max_length=150, blank=True)
    manufacturer = models.CharField('Производитель', max_length=150, blank=True)
    entrance = models.CharField('Подъезд', max_length=50, blank=True)
    floors = models.PositiveSmallIntegerField('Остановок', default=1)
    capacity_kg = models.PositiveIntegerField('Грузоподъёмность, кг', null=True, blank=True)
    elevator_type = models.CharField('Тип', max_length=20, choices=ElevatorType.choices, default=ElevatorType.PASSENGER)
    assigned_technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='elevators')
    active = models.BooleanField('На обслуживании', default=True)
    notes = models.TextField('Примечание', blank=True)

    class Meta:
        ordering = ['building__address', 'entrance', 'factory_number']
        verbose_name = 'Лифт'
        verbose_name_plural = 'Лифты'

    def __str__(self):
        return f'{self.factory_number} — {self.building.address}'


class Ticket(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Низкий'
        NORMAL = 'NORMAL', 'Обычный'
        HIGH = 'HIGH', 'Высокий'
        EMERGENCY = 'EMERGENCY', 'Аварийный'

    class Status(models.TextChoices):
        NEW = 'NEW', 'Новая'
        ASSIGNED = 'ASSIGNED', 'Назначена'
        IN_PROGRESS = 'IN_PROGRESS', 'В работе'
        DONE = 'DONE', 'Выполнена'
        CANCELED = 'CANCELED', 'Отменена'

    elevator = models.ForeignKey(Elevator, on_delete=models.CASCADE, related_name='tickets')
    title = models.CharField('Кратко', max_length=200)
    description = models.TextField('Описание', blank=True)
    priority = models.CharField('Приоритет', max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'

    def __str__(self):
        return f'#{self.pk or "—"} {self.title}'


class Maintenance(models.Model):
    class Kind(models.TextChoices):
        TO1 = 'TO1', 'ТО-1'
        TO2 = 'TO2', 'ТО-2'
        REPAIR = 'REPAIR', 'Ремонт'
        INSPECTION = 'INSPECTION', 'Осмотр'

    elevator = models.ForeignKey(Elevator, on_delete=models.CASCADE, related_name='maintenance')
    technician = models.ForeignKey(Technician, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance')
    kind = models.CharField('Вид работы', max_length=20, choices=Kind.choices, default=Kind.TO1)
    planned_date = models.DateField('Плановая дата', db_index=True)
    completed_at = models.DateTimeField('Выполнено', null=True, blank=True)
    notes = models.TextField('Результат/замечания', blank=True)

    class Meta:
        ordering = ['planned_date']
        verbose_name = 'ТО'
        verbose_name_plural = 'ТО'

    def __str__(self):
        return f'{self.get_kind_display()} {self.elevator} — {self.planned_date}'
