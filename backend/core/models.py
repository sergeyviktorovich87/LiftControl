from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import uuid


class Organization(models.Model):
    name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, default="Asia/Yakutsk")
    def __str__(self):
        return self.name



class Building(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, default=1, db_default=1)
    name = models.CharField('Объект', max_length=200)
    street = models.CharField('Улица', max_length=200, blank=True, db_default='')
    house = models.CharField('Дом', max_length=50, blank=True, db_default='')
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
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, default=1, db_default=1)
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
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, default=1, db_default=1)
    class ElevatorType(models.TextChoices):
        PASSENGER = 'PASSENGER', 'Пассажирский'
        FREIGHT = 'FREIGHT', 'Грузовой'
        HOSPITAL = 'HOSPITAL', 'Больничный'
        SERVICE = 'SERVICE', 'Малый грузовой'

    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name='elevators')
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
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, default=1, db_default=1)
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

    elevator = models.ForeignKey(Elevator, on_delete=models.PROTECT, related_name='tickets')
    repair = models.TextField('Выполненные работы', blank=True, max_length=4000, db_default='')
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
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, default=1, db_default=1)
    class Kind(models.TextChoices):
        TO1 = 'TO1', 'ТО-1'
        TO2 = 'TO2', 'ТО-2'
        REPAIR = 'REPAIR', 'Ремонт'
        INSPECTION = 'INSPECTION', 'Осмотр'

    elevator = models.ForeignKey(Elevator, on_delete=models.PROTECT, related_name='maintenance')
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



class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Администратор'
        DIRECTOR = 'DIRECTOR', 'Директор'
        DISPATCHER = 'DISPATCHER', 'Диспетчер'
        MECHANIC = 'MECHANIC', 'Механик'
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='membership')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MECHANIC)
    technician = models.OneToOneField(Technician, null=True, blank=True, on_delete=models.SET_NULL)
    active = models.BooleanField(default=True)
    def clean(self):
        if self.technician and self.technician.organization_id != self.organization_id:
            raise ValidationError('Сотрудник должен принадлежать той же организации.')
        if self.role == self.Role.MECHANIC and not self.technician:
            raise ValidationError('Для механика выберите сотрудника.')


def private_path(instance, filename):
    return f'{instance.organization_id}/{uuid.uuid4().hex}'


class TicketPhoto(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name='photos')
    file = models.FileField(upload_to=private_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)


class DutyShift(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    technician = models.ForeignKey(Technician, on_delete=models.PROTECT)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=20, default='daily', choices=[('daily','Сутки'),('day','День'),('night','Ночь'),('custom','Своя смена')])
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['start','id']
        constraints = [models.CheckConstraint(condition=models.Q(end__gt=models.F('start')), name='duty_end_after_start')]


class PartRequest(models.Model):
    class Status(models.TextChoices):
        NEW = 'NEW', 'Новая'
        APPROVED = 'APPROVED', 'Согласована'
        ORDERED = 'ORDERED', 'Заказана'
        RECEIVED = 'RECEIVED', 'Получена'
        ISSUED = 'ISSUED', 'Выдана'
        CANCELED = 'CANCELED', 'Отменена'
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    elevator = models.ForeignKey(Elevator, on_delete=models.PROTECT)
    part = models.CharField('Запчасть', max_length=250)
    quantity = models.PositiveSmallIntegerField('Количество', default=1)
    notes = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']


class ChatMessage(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['created_at','id']


class Document(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=150)
    model = models.CharField(max_length=150, blank=True)
    file = models.FileField(upload_to=private_path)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['title']


class AuditEvent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
