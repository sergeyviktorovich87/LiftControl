"""A person's choices are scoped to one employer and checked again before delivery."""
from zoneinfo import ZoneInfo

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .access import MemberAccess, org
from .models import (
    CommissioningAssignment, CommissioningProgress, CommissioningProject,
    DutyShift, Membership, NotificationPreference,
)

CATEGORIES = ('ordinary', 'urgent', 'entrapment', 'updates', 'tasks')
FIELDS = (*CATEGORIES, 'only_mine', 'quiet_enabled', 'quiet_start', 'quiet_end', 'muted_weekdays')
NEW_TICKET_EVENTS = ('created', 'reassigned')


def ticket_recipients(ticket, kind):
    members = Membership.objects.filter(
        organization=ticket.organization, active=True, user__is_active=True,
    ).exclude(role='ADJUSTER').exclude(
        role='MECHANIC', technician__isnull=True,
    ).exclude(role='MECHANIC', technician__active=False)
    responsible = ticket.assigned_to_id or ticket.elevator.assigned_technician_id
    eligible = Q(role__in=('ADMIN', 'DIRECTOR', 'DISPATCHER'))
    if responsible:
        eligible |= Q(role='MECHANIC', technician_id=responsible)
    if ticket.priority in ('HIGH', 'EMERGENCY', 'ENTRAPMENT') or not responsible:
        now = timezone.now()
        on_duty = DutyShift.objects.filter(
            organization=ticket.organization, start__lte=now, end__gt=now,
        ).values('technician_id')
        eligible |= Q(role='MECHANIC', technician_id__in=on_duty)
    if kind in NEW_TICKET_EVENTS and responsible and ticket.priority in ('LOW', 'NORMAL'):
        eligible = Q(role='MECHANIC', technician_id=responsible)
    return members.filter(eligible)


def category(priority, kind='created'):
    if kind not in ('created','reassigned'):
        return 'updates'
    return 'entrapment' if priority == 'ENTRAPMENT' else 'urgent' if priority in ('HIGH','EMERGENCY') else 'ordinary'


def personal_ticket(ticket, user_id, now=None):
    if ticket.created_by_id == user_id:
        return True
    team = Membership.objects.filter(
        user_id=user_id, organization_id=ticket.organization_id, active=True,
        technician__active=True, technician__organization_id=ticket.organization_id,
    )
    responsible = ticket.assigned_to_id or ticket.elevator.assigned_technician_id
    if responsible and team.filter(technician_id=responsible).exists():
        return True
    if responsible and ticket.priority not in ('HIGH', 'EMERGENCY', 'ENTRAPMENT'):
        return False
    current = now or timezone.now()
    return DutyShift.objects.filter(
        organization_id=ticket.organization_id, start__lte=current, end__gt=current,
        technician_id__in=team.filter(role='MECHANIC').values('technician_id'),
    ).exists()


def personal_commissioning(item):
    if CommissioningProject.objects.filter(
        pk=item.target_id, organization_id=item.organization_id, created_by_id=item.user_id,
    ).exists():
        return True
    assignments = CommissioningAssignment.objects.filter(
        lift__project_id=item.target_id, lift__project__organization_id=item.organization_id,
        user_id=item.user_id, active=True,
    )
    if item.kind == 'progress':
        assignments = assignments.filter(lift_id__in=CommissioningProgress.objects.filter(
            pk=item.event_id, lift__project_id=item.target_id,
        ).values('lift_id'))
    return assignments.exists()


def preferences_allow(row, group, *, personal=True, now=None):
    if row is None:
        return True
    if group and not getattr(row, group):
        return False
    if row.quiet_enabled or row.muted_weekdays:
        local = (now or timezone.now()).astimezone(ZoneInfo(row.organization.timezone))
        if local.weekday() in row.muted_weekdays:
            return False
        if row.quiet_enabled:
            start, end = row.quiet_start, row.quiet_end
            clock = local.time()
            quiet = start <= clock < end if start < end else clock >= start or clock < end
            if quiet:
                return False
    return not row.only_mine or (personal() if callable(personal) else personal)


def allows(user_id, organization_id, group, *, personal=True, now=None):
    row = NotificationPreference.objects.select_related('organization').filter(
        user_id=user_id, organization_id=organization_id,
    ).first()
    return preferences_allow(row, group, personal=personal, now=now)


class PreferenceSerializer(serializers.ModelSerializer):
    quiet_start = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'], required=False)
    quiet_end = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'], required=False)
    muted_weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        max_length=7, required=False,
    )

    class Meta:
        model = NotificationPreference
        fields = FIELDS

    def validate_muted_weekdays(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError('Выберите каждый день только один раз.')
        return sorted(values)

    def validate(self, attrs):
        current = self.instance
        if attrs.get('quiet_enabled', current.quiet_enabled):
            start = attrs.get('quiet_start', current.quiet_start)
            end = attrs.get('quiet_end', current.quiet_end)
            if start == end:
                raise serializers.ValidationError({'quiet_end': 'Время окончания должно отличаться от времени начала.'})
        return attrs


@api_view(['GET', 'PATCH'])
@permission_classes([MemberAccess])
def preferences(request):
    organization = org(request.user)
    lookup = {'user': request.user, 'organization': organization}
    if request.method == 'GET':
        row = NotificationPreference.objects.filter(**lookup).first() or NotificationPreference(**lookup)
        return Response(PreferenceSerializer(row).data, headers={'Cache-Control': 'private, no-store'})

    with transaction.atomic():
        row, _ = NotificationPreference.objects.select_for_update().get_or_create(**lookup)
        serializer = PreferenceSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(serializer.data, headers={'Cache-Control': 'private, no-store'})
