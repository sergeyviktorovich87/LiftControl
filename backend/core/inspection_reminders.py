from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import Elevator, InspectionReminder, Membership, NotificationInbox, Organization
from .notification_inbox import _enqueue


def enqueue_due_inspections(now=None):
    now = now or timezone.now()
    delivered = 0
    for company in Organization.objects.all().only('id', 'timezone'):
        local = now.astimezone(ZoneInfo(company.timezone))
        if local.hour < 9:
            continue
        today = local.date()
        candidates = Elevator.objects.filter(
            organization=company, active=True, assigned_technician__active=True,
            assigned_technician__organization=company, next_inspection_on__gt=today,
            next_inspection_on__lte=today + timedelta(days=5),
        )
        for elevator_id in candidates.values_list('pk', flat=True).iterator():
            with transaction.atomic():
                elevator = (candidates.filter(pk=elevator_id).select_related('building')
                            .select_for_update(of=('self',)).first())
                if elevator is None:
                    continue
                recipients = list(Membership.objects.filter(
                    organization=company, role='MECHANIC', technician_id=elevator.assigned_technician_id,
                    active=True, user__is_active=True,
                ).values_list('user_id', flat=True))
                if not recipients:
                    continue
                reminder, _ = InspectionReminder.objects.get_or_create(
                    elevator=elevator, inspection_on=elevator.next_inspection_on, reminder_on=today,
                )
                served = NotificationInbox.objects.filter(
                    event_type='inspection', event_id=reminder.pk,
                ).values_list('user_id', flat=True)
                remaining = set(recipients) - set(served)
                if not remaining:
                    continue
                date = reminder.inspection_on.strftime('%d.%m.%Y')
                entrance = f' · подъезд {elevator.entrance}' if elevator.entrance else ''
                title = f'Освидетельствование {date} · {elevator.building.address}{entrance}'
                _enqueue(company, remaining, 'inspection', reminder.pk, 'reminder', title,
                         'inspection', elevator.pk, push=True, body=f'{title}\nЛифт {elevator.display_number}')
                delivered += len(remaining)
    return delivered
