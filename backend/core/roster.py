"""Read, configure and publish the organization's daily duty rotation."""
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.serializers import DateField

from .access import ManagerWrite, MemberAccess, audit, manager, org
from .models import DutyRoster, DutyShift, Organization, Technician

DAY = timedelta(days=1)


def date_value(value):
    return DateField().run_validation(value)


def days_between(first, last):
    count = (last - first).days + 1
    if not 1 <= count <= 366 or last.year >= 9999:
        raise ValidationError('Выберите период от 1 до 366 дней.')
    return [first + i * DAY for i in range(count)]


def active_mechanics(organization):
    return {row.pk: row.full_name for row in Technician.objects.filter(
        organization=organization, active=True, role='MECHANIC')}


def get_config(organization):
    return DutyRoster.objects.filter(organization=organization).values_list('config', flat=True).first() or {
        'cycles': [], 'periods': [],
    }


def on_leave(config, technician_id, first, end, organization):
    if not config['periods']:
        return False
    zone = ZoneInfo(organization.timezone)
    first = first.astimezone(zone).date()
    # A normal daily shift ends at the start of the next duty day.
    end = end.astimezone(zone)
    last = end.date() - DAY if end.time() <= organization.duty_start else end.date()
    last = max(first, last)
    return any(rule['type'] == 'leave' and rule['worker'] == technician_id
               and rule['from'] <= last.isoformat() and first.isoformat() <= rule['to']
               for rule in config['periods'])


def validate_config(payload, organization):
    if not isinstance(payload, dict):
        raise ValidationError('Некорректные настройки графика.')
    mechanics = active_mechanics(organization)
    today = timezone.localdate(timezone=ZoneInfo(organization.timezone))
    current = get_config(organization)
    data = {}
    for key in ('cycles', 'periods'):
        raw = payload.get(key)
        if not isinstance(raw, list) or len(raw) > 120 or any(not isinstance(row, dict) for row in raw):
            raise ValidationError('Допустимо до 120 записей каждого типа.')
        history = [row for row in current[key] if row['from'] <= today.isoformat()]
        # Past or currently effective rules remain immutable. New rules start tomorrow.
        if [row for row in raw if row in history] != history:
            raise ValidationError('Действующие и прошедшие правила сохраняются в истории.')
        output = list(history)
        for row in raw:
            if row in history:
                continue
            first = date_value(row.get('from'))
            if first <= today:
                raise ValidationError('Новое правило должно начинаться с завтрашнего дня или позже.')
            rule = {'from': first.isoformat()}
            kind = 'cycle' if key == 'cycles' else row.get('type')
            if kind not in ('cycle', 'temp', 'leave', 'replace') or (key == 'periods' and kind == 'cycle'):
                raise ValidationError('Выберите тип периода.')
            if kind != 'cycle':
                last = date_value(row.get('to'))
                days_between(first, last)
                rule.update(type=kind, to=last.isoformat())
            if kind in ('cycle', 'temp'):
                ids = row.get('people')
                if not isinstance(ids, list) or not ids or any(type(x) is not int or x not in mechanics for x in ids) or len(set(ids)) != len(ids):
                    raise ValidationError('Выберите действующих механиков для очереди без повторов.')
                rule['people'] = ids
            else:
                worker, target = row.get('worker'), row.get('target')
                if type(worker) is not int or worker not in mechanics or (kind == 'replace' and
                        (type(target) is not int or target not in mechanics or target == worker)):
                    raise ValidationError('Выберите действующих механиков.')
                rule['worker'] = worker
                if kind == 'replace':
                    rule['target'] = target
            for old in output:
                conflicts = old['from'] == rule['from'] if kind == 'cycle' else (
                    old['type'] == kind and old.get('worker') == rule.get('worker')
                    and old['from'] <= rule['to'] and rule['from'] <= old['to'])
                if conflicts:
                    raise ValidationError('Даты пересекаются с другим правилом того же типа.')
            output.append(rule)
        data[key] = sorted(output, key=lambda row: row['from'])
    return data


def suggestion(day, config, mechanics):
    value = day.isoformat()
    cycle = next((rule for rule in reversed(config['cycles']) if rule['from'] <= value), None)
    periods = [rule for rule in config['periods'] if rule['from'] <= value <= rule['to']]
    cycle = next((rule for rule in periods if rule['type'] == 'temp'), cycle)
    if not cycle:
        return None, False
    people = cycle['people']
    candidate = people[(day - date.fromisoformat(cycle['from'])).days % len(people)]
    target = next((rule['target'] for rule in periods
                   if rule['type'] == 'replace' and rule['worker'] == candidate), candidate)
    if target not in mechanics or any(rule['type'] == 'leave' and rule['worker'] == target for rule in periods):
        return None, False
    return target, target != candidate


def roster_days(organization, dates, config, include_plan, *, replace_existing=False):
    zone = ZoneInfo(organization.timezone)
    now = timezone.now()
    mechanics = active_mechanics(organization) if include_plan else {}
    first = datetime.combine(dates[0], datetime.min.time(), zone)
    last = datetime.combine(dates[-1] + DAY, organization.duty_start, zone)
    shifts = list(DutyShift.objects.filter(organization=organization,
                  start__lt=last, end__gt=first).select_related('technician').prefetch_related('swaps'))
    for day in dates:
        start = datetime.combine(day, organization.duty_start, zone)
        end = start + DAY
        conflicts = [row for row in shifts if row.start < end and row.end > start]
        own = [row for row in shifts if row.start.astimezone(zone).date() == day]
        planned = None
        replacement = False
        if include_plan and start > now:
            planned, replacement = suggestion(day, config, mechanics)
        generated = None
        if len(conflicts) == 1:
            row = conflicts[0]
            if ((row.roster_generated or replace_existing) and row.kind == 'daily'
                    and row.start == start and row.end == end and not any(row.swaps.all())):
                generated = row
        change = include_plan and start > now and ((not conflicts and planned) or (
            generated and planned and planned != generated.technician_id))
        needs = include_plan and start > now and not planned and (not conflicts or generated is not None)
        if include_plan and start > now and any(
            on_leave(config, row.technician_id, row.start, row.end, organization) for row in own
            if row.pk != getattr(generated, 'pk', None)
        ):
            needs = True
        yield day, start, end, own, conflicts, generated, planned, replacement, bool(change), needs


@api_view(['GET'])
@permission_classes([MemberAccess])
def roster(request):
    organization = org(request.user)
    dates = days_between(date_value(request.query_params.get('from')), date_value(request.query_params.get('to')))
    include_plan = manager(request.user)
    config = get_config(organization)
    mechanics = active_mechanics(organization) if include_plan else {}
    rows = []
    for day, start, end, own, conflicts, generated, planned, replacement, change, needs in roster_days(
        organization, dates, config, include_plan
    ):
        rows.append({
            'date': day, 'start': start.isoformat(), 'end': end.isoformat(),
            'shifts': [{'id': shift.pk, 'technician': shift.technician_id, 'technician_name': shift.technician.full_name,
                        'start': shift.start.isoformat(), 'end': shift.end.isoformat(), 'kind': shift.kind,
                        'pending_swap': any(swap.status == 'PENDING' for swap in shift.swaps.all())} for shift in own],
            'covered_from_previous': bool(conflicts and conflicts[0] not in own),
            'suggested': planned if change else None,
            'suggested_name': mechanics.get(planned) if change else None,
            'replacement': replacement if change else False,
            'needs_assignment': needs,
            'unavailable': [pk for pk in mechanics if on_leave(config, pk, start, end, organization)],
        })
    return Response(rows, headers={'Cache-Control': 'private, no-store'})


@api_view(['GET', 'PUT'])
@permission_classes([ManagerWrite])
def settings(request):
    if not manager(request.user):
        raise PermissionDenied()
    organization = org(request.user)
    if request.method == 'GET':
        return Response(get_config(organization), headers={'Cache-Control': 'private, no-store'})
    if not isinstance(request.data, dict):
        raise ValidationError('Некорректные настройки графика.')
    with transaction.atomic():
        organization = Organization.objects.select_for_update().get(pk=organization.pk)
        if request.data.get('previous') != get_config(organization):
            raise ValidationError('График изменился. Откройте настройки заново.')
        config = validate_config(request.data.get('config'), organization)
        DutyRoster.objects.update_or_create(organization=organization, defaults={'config': config})
        audit(request.user, 'duty.roster.settings', organization.pk, config)
    return Response(config, headers={'Cache-Control': 'private, no-store'})


@api_view(['POST'])
@permission_classes([ManagerWrite])
def publish(request):
    if not isinstance(request.data, dict):
        raise ValidationError('Выберите месяц.')
    organization = org(request.user)
    first = date_value(request.data.get('from'))
    last = date_value(request.data.get('to'))
    dates = days_between(first, last)
    preview = request.data.get('preview') is True
    token = request.data.get('token')
    reviewed = preview or 'token' in request.data
    replace_existing = reviewed and request.data.get('replace_existing') is True
    if not reviewed and (first.day != 1 or last.month != first.month or (last + DAY).month == last.month):
        raise ValidationError('Для публикации выберите целый месяц.')
    with transaction.atomic():
        organization = Organization.objects.select_for_update().get(pk=organization.pk)
        entries = list(roster_days(organization, dates, get_config(organization), True,
                                   replace_existing=replace_existing))
        missing = [day.strftime('%d.%m.%Y') for day, _, _, _, _, _, _, _, _, needs in entries if needs]
        if reviewed:
            mechanics = active_mechanics(organization)
            changes = [{
                'date': day.isoformat(), 'shift': shift.pk if shift else None,
                'old_id': shift.technician_id if shift else None, 'new_id': planned,
                'old_name': shift.technician.full_name if shift else None, 'new_name': mechanics.get(planned),
            } for day, _, _, _, _, shift, planned, _, change, _ in entries if change]
            fingerprint = sha256(json.dumps([organization.pk, request.user.pk, first.isoformat(),
                                 last.isoformat(), replace_existing, missing, changes],
                                 sort_keys=True).encode()).hexdigest()
            salt = 'core.duty.roster-publication'
            if preview:
                added = sum(not change['shift'] for change in changes)
                return Response({'added': added, 'updated': len(changes) - added, 'missing': missing,
                                 'changes': [{key: row[key] for key in ('date', 'old_name', 'new_name')} for row in changes],
                                 'token': signing.dumps(fingerprint, salt=salt)})
            try:
                valid = isinstance(token, str) and signing.loads(token, salt=salt, max_age=1800) == fingerprint
            except signing.BadSignature:
                valid = False
            if not valid:
                raise ValidationError('График изменился или проверка устарела. Проверьте даты ещё раз.')
        if missing:
            raise ValidationError('Назначьте дежурных на даты: ' + ', '.join(missing))
        added, changed = [], []
        for day, start, end, _, _, generated, planned, _, change, _ in entries:
            if not change:
                continue
            if generated:
                changed.append({'id': generated.pk, 'from': generated.technician_id, 'to': planned})
                generated.technician_id = planned
                generated.save(update_fields=['technician', 'updated_at'])
            else:
                added.append(DutyShift(organization=organization, technician_id=planned, start=start,
                                       end=end, kind='daily', roster_generated=True))
        DutyShift.objects.bulk_create(added)
        if added or changed:
            audit(request.user, 'duty.roster.publish', first.isoformat(), {'added': len(added), 'changes': changed})
    return Response({'added': len(added), 'updated': len(changed)})
