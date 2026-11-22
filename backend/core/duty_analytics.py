from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.serializers import DateField, ValidationError

from .access import MemberAccess, admin_user, org
from .models import DutyShift, DutySwap, Technician


@api_view(['GET'])
@permission_classes([MemberAccess])
def summary(request):
    if not admin_user(request.user):
        raise PermissionDenied('Аналитика доступна администратору.')
    company = org(request.user)
    zone = ZoneInfo(company.timezone)
    now = timezone.now()
    today = now.astimezone(zone).date()
    date_field = DateField()
    start = date_field.run_validation(request.query_params.get('from', today.replace(day=1).isoformat()))
    end = date_field.run_validation(request.query_params.get('to', today.isoformat()))
    if not 0 <= (end - start).days < 366 or end.year >= 9999:
        raise ValidationError('Выберите период до 366 дней.')
    first = datetime.combine(start, time.min, zone)
    last = datetime.combine(end + timedelta(days=1), time.min, zone)
    shifts = DutyShift.objects.filter(organization=company, start__gte=first, start__lt=last)
    rows = {
        row['technician_id']: {
            'id': row['technician_id'], 'name': row['technician__full_name'],
            'completed': row['completed'], 'planned': row['total'] - row['completed'],
            'swaps_in': 0, 'swaps_out': 0,
        }
        for row in shifts.order_by().values('technician_id', 'technician__full_name').annotate(
            total=Count('pk'), completed=Count('pk', filter=Q(end__lte=now)))
    }
    swaps = DutySwap.objects.filter(organization=company, shift__in=shifts, status='ACCEPTED').select_related(
        'shift', 'source_technician', 'target_technician').order_by('-shift__start', '-pk')
    accepted = []
    for swap in swaps:
        for tech, key in ((swap.source_technician, 'swaps_out'), (swap.target_technician, 'swaps_in')):
            row = rows.setdefault(tech.pk, {'id': tech.pk, 'name': tech.full_name, 'completed': 0,
                                           'planned': 0, 'swaps_in': 0, 'swaps_out': 0})
            row[key] += 1
        accepted.append({'id': swap.pk, 'start': swap.shift.start.isoformat(), 'source': swap.source_technician.full_name,
                         'target': swap.target_technician.full_name})
    for tech in Technician.objects.filter(organization=company, active=True, role='MECHANIC'):
        rows.setdefault(tech.pk, {'id': tech.pk, 'name': tech.full_name, 'completed': 0,
                                 'planned': 0, 'swaps_in': 0, 'swaps_out': 0})
    return Response({'from': start.isoformat(), 'to': end.isoformat(),
                     'technicians': sorted(rows.values(), key=lambda row: row['name'].casefold()), 'swaps': accepted},
                    headers={'Cache-Control': 'private, no-store'})
