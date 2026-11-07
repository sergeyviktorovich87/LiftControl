"""Explicit, backed-up replacement of pilot work data with the supplied 157 units."""
import os
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from core.megapolis_data import GROUPS, SOURCE, validate_source
from core.models import (Organization, Membership, Building, Technician, Elevator,
    Ticket, TicketPhoto, TicketEvent, TicketComment, Maintenance, DutyShift, DutySwap,
    PartRequest, ChatMessage, Document, PushDelivery, AuditEvent)


class Command(BaseCommand):
    help = 'Preview or import Megapolis; preserve accounts and organization access.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--replace-work-data', action='store_true')
        parser.add_argument('--backup', help='New private JSON backup file, required before deleting work data.')

    def handle(self, *args, **options):
        validate_source()
        marker = 'data.megapolis_imported_v1'
        if AuditEvent.objects.filter(action=marker).exists():
            self.stdout.write('Список уже импортирован. Повторная очистка запрещена; изменений нет.')
            return
        addresses = {(street,house) for _,_,rows in GROUPS for street,house,_,_ in rows}
        self.stdout.write(f'{SOURCE}: 157 единиц, {len(addresses)} адресных карточек. Только Мегаполис.')
        for name, count, _ in GROUPS:
            self.stdout.write(f'  {name}: {count}')
        self.stdout.write('Подъезды, заводские номера и остановки неизвестны. Этажность сохранится отдельно.')
        if not options['apply']:
            self.stdout.write(f'Предпросмотр: сейчас в базе {Elevator.objects.count()} единиц; записи не изменены.')
            return
        if not options['replace_work_data'] or not options['backup']:
            raise CommandError('Нужны --replace-work-data и --backup: удаляются пилотные заявки, объекты, графики, чат, документы, запчасти и ТО; аккаунты остаются.')
        backup = Path(options['backup'])
        try:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise CommandError('Не удалось создать новый закрытый файл резервной копии.') from exc
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                call_command('dumpdata', stdout=output, verbosity=0)
                output.flush()
                os.fsync(output.fileno())
        except Exception as exc:
            raise CommandError('Резервная копия не завершена. Очистка НЕ начата.') from exc
        if backup.stat().st_size < 2:
            raise CommandError('Пустая резервная копия. Очистка НЕ начата.')
        with transaction.atomic():
            list(Organization.objects.select_for_update().order_by('pk'))
            if AuditEvent.objects.filter(action=marker).exists():
                self.stdout.write('Список уже импортирован другим процессом. Изменений нет.')
                return
            for model in (PushDelivery, TicketPhoto, TicketEvent, TicketComment, Ticket,
                          Maintenance, PartRequest, DutySwap, DutyShift, ChatMessage, Document, Elevator, Building):
                model.objects.all().delete()
            # Keep linked employee identities so existing logins and invitations remain valid.
            Technician.objects.filter(membership__isnull=True,organizationinvite__isnull=True).delete()
            company, _ = Organization.objects.get_or_create(name='Мегаполис', defaults={'timezone':'Asia/Yakutsk','duty_start':'09:00'})
            Organization.objects.get_or_create(name='ООО «Эверест»', defaults={'timezone':'Asia/Yakutsk','duty_start':'09:00'})
            company.duty_start = '09:00'
            company.save(update_fields=['duty_start'])
            owner_roles = {}
            for user_id,access_role in Membership.objects.filter(active=True,role__in=['ADMIN','DIRECTOR'],user__is_active=True).values_list('user_id','role'):
                if user_id not in owner_roles or access_role=='ADMIN':
                    owner_roles[user_id]=access_role
            for user_id in get_user_model().objects.filter(is_superuser=True,is_active=True).values_list('pk',flat=True):
                owner_roles[user_id]='ADMIN'
            for user_id,access_role in owner_roles.items():
                Membership.objects.get_or_create(user_id=user_id,organization=company,defaults={'role':access_role})
            created, warnings = 0, []
            for group_no, (name, expected, rows) in enumerate(GROUPS, 1):
                tech, _ = Technician.objects.get_or_create(organization=company,full_name=name,defaults={'role':'MECHANIC'})
                for row_no,(street, house, batches, note) in enumerate(rows,1):
                    address = (street+' '+house).strip()
                    building, _ = Building.objects.get_or_create(organization=company,street=street,house=house,
                        defaults={'address':address,'name':address})
                    if note:
                        warnings.append(address+': '+note)
                    row_index = 0
                    for building_floors, count in batches:
                        for _ in range(count):
                            row_index += 1
                            created += 1
                            Elevator.objects.create(organization=company,building=building,assigned_technician=tech,
                                factory_number=None,inventory_number=f'МГП-{created:03}',entrance='',floors=None,
                                building_floors=building_floors,elevator_type='PLATFORM' if 'Подъёмник' in note else 'UNKNOWN',
                                source_reference=f'{SOURCE}; группа {group_no}, строка {row_no}, единица {row_index}',
                                notes='Из исходной таблицы: подъезд, заводской номер и число остановок требуют заполнения. '+note)
                if Elevator.objects.filter(organization=company,assigned_technician=tech).count() != expected:
                    raise CommandError('Количество по механику не совпало. Транзакция отменена.')
            if created != 157 or Elevator.objects.count() != 157:
                raise CommandError('Общее количество не совпало. Транзакция отменена.')
            AuditEvent.objects.create(organization=company,action=marker,object_id=str(created),
                details={'source':SOURCE,'counts':{name:n for name,n,_ in GROUPS},'warnings':warnings})
        self.stdout.write(self.style.SUCCESS(f'Импортировано {created}. Резервная копия: {backup}. Аккаунты сохранены.'))
        for issue in warnings:
            self.stdout.write('УТОЧНИТЬ: '+issue)
