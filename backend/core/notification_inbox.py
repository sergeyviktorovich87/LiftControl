"""Server-owned notification history.

Inbox records are not delivery acknowledgments, and marking as read must
never accept a ticket or task. Push transports can fail independently of this
history; privacy is enforced at creation and again at read time.
"""
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.serializers import BooleanField, ChoiceField, IntegerField, Serializer

from .access import MemberAccess, org, role, technician_id, commissioning_access
from .models import Membership, NotificationInbox, CommissioningAssignment, CommissioningMessage, CommissioningProgress, PersonalTask
from .models import InspectionReminder

SECTION_BY_TARGET = {
    'ticket': 'tickets', 'task': 'tasks', 'commissioning': 'commissioning',
    'commissioning_chat': 'commissioning', 'part': 'parts', 'chat': 'chat',
    'inspection': 'elevators',
}


def _enqueue(organization, user_ids, event_type, event_id, kind, title,
             target_type, target_id, *, push=False, is_entrapment=False):
    unique={int(uid) for uid in user_ids if uid}
    NotificationInbox.objects.bulk_create([
        NotificationInbox(organization=organization, user_id=uid,
                          event_type=event_type, event_id=event_id,
                          kind=kind, title=title[:200],
                          target_type=target_type, target_id=target_id,
                          is_entrapment=is_entrapment,
                          commissioning_push_after=timezone.now() if push else None)
        for uid in unique
    ], ignore_conflicts=True)


def enqueue_ticket(event):
    from .notification_preferences import ticket_recipients
    ticket=event.ticket
    users = ticket_recipients(ticket, event.action).values_list('user_id', flat=True)
    _enqueue(ticket.organization,users,'ticket',event.pk,event.action,
             f'Заявка №{ticket.pk}: {event.action}','ticket',ticket.pk,
             is_entrapment=ticket.priority == 'ENTRAPMENT')


def enqueue_task(event):
    task=event.task
    users=set()
    if task.created_by_id:
        users.add(task.created_by_id)
    assigned=Membership.objects.filter(
        organization=task.organization,active=True,user__is_active=True,
        role='MECHANIC',technician=task.assigned_to,
        technician__active=True).values_list('user_id',flat=True)
    users.update(assigned)
    _enqueue(task.organization,users,'task',event.pk,event.action,
             f'Личное задание №{task.pk}: {event.action}','task',task.pk)


def _commissioning_recipients(project, author_id, *, lift_id=None):
    assignments = CommissioningAssignment.objects.filter(lift__project=project, active=True)
    if lift_id is not None:
        assignments = assignments.filter(lift_id=lift_id)
    members = Membership.objects.filter(
        organization=project.organization, active=True, user__is_active=True,
    ).exclude(role='MECHANIC', technician__isnull=True).exclude(
        role='MECHANIC', technician__active=False,
    ).filter(
        Q(technician__isnull=True) | Q(technician__organization=project.organization),
    )
    return members.filter(
        Q(role__in=['ADMIN', 'DIRECTOR']) |
        Q(can_commissioning=True, user_id__in=assignments.values('user_id')),
    ).exclude(user_id=author_id).values_list('user_id', flat=True)


def enqueue_commissioning_message(message):
    project = message.project
    _enqueue(project.organization, _commissioning_recipients(project, message.author_id),
             'commissioning_message', message.pk, 'message',
             f'Сообщение на объекте: {project.name}', 'commissioning', project.pk, push=True)


def enqueue_commissioning_progress(event):
    project = event.lift.project
    users = _commissioning_recipients(project, event.actor_id, lift_id=event.lift_id)
    _enqueue(project.organization, users, 'commissioning_progress', event.pk, 'progress',
             f'Комментарий по наладке: {project.name} · {event.lift.label}',
             'commissioning', project.pk, push=True)


def enqueue_commissioning_chat(message):
    members = Membership.objects.filter(
        organization=message.organization, active=True, user__is_active=True,
    ).exclude(role='MECHANIC', technician__isnull=True).exclude(
        role='MECHANIC', technician__active=False,
    ).filter(
        Q(technician__isnull=True) | Q(technician__organization_id=message.organization_id),
    ).filter(
        Q(role__in=['ADMIN', 'DIRECTOR']) | Q(can_commissioning=True),
    ).exclude(user_id=message.author_id)
    _enqueue(message.organization, members.values_list('user_id', flat=True),
             'commissioning_team_chat', message.pk, 'message',
             'Новое сообщение в чате наладчиков', 'commissioning_chat', message.pk, push=True)


def enqueue_part(part, event, *, created):
    if created:
        recipients = Membership.objects.filter(
            organization=part.organization, active=True, user__is_active=True,
            role__in=['ADMIN', 'DIRECTOR', 'DISPATCHER'],
        ).values_list('user_id', flat=True)
        title = f'Новая заявка на запчасть: {part.part}'
    else:
        recipients = [part.requested_by_id]
        title = f'Запчасть «{part.part}»: {part.get_status_display()}'
    _enqueue(part.organization, set(recipients) - {event.actor_id}, 'part',
             event.pk, 'created' if created else 'status', title, 'part', part.pk)


def enqueue_team_chat(message):
    # Regular team chat is not visible to restricted external adjusters.
    recipients=(Membership.objects.filter(
        organization=message.organization,active=True,user__is_active=True)
        .exclude(role='ADJUSTER')
        .exclude(role='MECHANIC',technician__isnull=True)
        .exclude(role='MECHANIC',technician__active=False)
        .exclude(user_id=message.author_id)
        .values_list('user_id',flat=True).distinct())
    _enqueue(message.organization,recipients,'team_chat',message.pk,'message',
             'Новое сообщение в чате команды','chat',message.pk)

def _visible_inbox(user, company):
    # An already-created inbox row is not a permanent access grant.
    rows = NotificationInbox.objects.filter(user=user, organization=company)
    current_role = role(user)
    if current_role == 'MECHANIC':
        inspections = InspectionReminder.objects.filter(
            elevator__organization=company, elevator__active=True,
            elevator__assigned_technician_id=technician_id(user),
            inspection_on=F('elevator__next_inspection_on'),
        ).values('pk')
        rows = rows.filter(~Q(target_type='inspection') | Q(event_id__in=inspections))
    else:
        rows = rows.exclude(target_type='inspection')
    projects = CommissioningAssignment.objects.filter(
        user=user, active=True,
        lift__project__organization=company,
    ).values_list('lift__project_id', flat=True)
    if not commissioning_access(user):
        rows = rows.exclude(target_type__in=['commissioning', 'commissioning_chat'])
    elif current_role not in ('ADMIN', 'DIRECTOR'):
        progress = CommissioningProgress.objects.filter(
            lift__project__organization=company, lift__assignments__user=user,
            lift__assignments__active=True,
        ).values('pk')
        rows = rows.filter(~Q(event_type='commissioning_progress') | Q(event_id__in=progress))
    if current_role == 'ADJUSTER':
        return rows.filter(Q(target_type='commissioning', target_id__in=projects) |
                           Q(target_type='commissioning_chat'))
    if current_role in ('ADMIN', 'DIRECTOR', 'DISPATCHER'):
        if current_role == 'DISPATCHER':
            return rows.filter(~Q(target_type='commissioning') |
                               Q(target_type='commissioning', target_id__in=projects))
        return rows
    if current_role != 'MECHANIC':
        return rows.none()
    # Personal task events become invisible if the assignment was revoked.
    tasks = PersonalTask.objects.filter(organization=company,
                                        assigned_to_id=technician_id(user)).values_list('pk', flat=True)
    return rows.filter(
        (~Q(target_type='commissioning') | Q(target_id__in=projects)) &
        (~Q(target_type='task') | Q(target_id__in=tasks))
    )


@api_view(['GET'])
@permission_classes([MemberAccess])
def counts(request):
    unread = _visible_inbox(request.user, org(request.user)).filter(read_at__isnull=True)
    sections = {section: 0 for section in SECTION_BY_TARGET.values()}
    total = entrapment = chat = 0
    for row in unread.order_by().values('target_type', 'is_entrapment').annotate(count=Count('pk')):
        target, count = row['target_type'], row['count']
        total += count
        if row['is_entrapment']:
            entrapment += count
        if target == 'commissioning_chat':
            chat += count
        if target in SECTION_BY_TARGET:
            sections[SECTION_BY_TARGET[target]] += count
    return Response({'unread': total, 'sections': sections, 'entrapment': entrapment,
                     'commissioning_chat': chat},
                    headers={'Cache-Control': 'private, no-store'})


class ChatReadThrough(Serializer):
    target = ChoiceField(choices=['chat', 'commissioning_chat'])
    through = IntegerField(min_value=1, max_value=2**63 - 1)
    only = BooleanField(default=False)


@api_view(['POST'])
@permission_classes([MemberAccess])
def read_chat(request):
    validated = ChatReadThrough(data=request.data)
    validated.is_valid(raise_exception=True)
    data = validated.validated_data
    bound = {'target_id' if data['only'] else 'target_id__lte': data['through']}
    updated = _visible_inbox(request.user, org(request.user)).filter(
        target_type=data['target'],
        read_at__isnull=True,
        **bound,
    ).update(read_at=timezone.now())
    return Response({'updated': updated})


@api_view(['GET'])
@permission_classes([MemberAccess])
def inbox(request):
    company=org(request.user)
    visible=_visible_inbox(request.user, company)
    category = request.query_params.get('category')
    if category not in (None, 'ordinary', 'entrapment'):
        raise ValidationError({'category': 'Укажите ordinary или entrapment.'})
    unread_by_category = {
        row['is_entrapment']: row['count'] for row in visible.filter(read_at__isnull=True)
        .order_by().values('is_entrapment').annotate(count=Count('pk'))
    }
    if category is not None:
        visible = visible.filter(is_entrapment=category == 'entrapment')
    unread_count = (sum(unread_by_category.values()) if category is None else
                    unread_by_category.get(category == 'entrapment', 0))
    unread=request.query_params.get('unread')
    if unread not in (None,'0','1'):
        raise ValidationError({'unread':'Укажите 0 или 1.'})
    if unread == '1':
        visible=visible.filter(read_at__isnull=True)
    try:
        limit=int(request.query_params.get('limit','50'))
    except (ValueError,TypeError):
        raise ValidationError({'limit':'Неверное количество записей.'})
    if limit<1 or limit>100:
        raise ValidationError({'limit':'Допустимое количество: 1-100.'})
    rows=list(visible.order_by('-created_at','-id')[:limit])
    message_ids = [row.event_id for row in rows
                   if row.event_type in ('commissioning_message', 'commissioning_team_chat')]
    progress_ids = [row.event_id for row in rows if row.event_type == 'commissioning_progress']
    messages = dict(CommissioningMessage.objects.filter(
        Q(project__organization=company) | Q(organization=company), pk__in=message_ids,
    ).values_list('id', 'text'))
    progress = dict(CommissioningProgress.objects.filter(
        pk__in=progress_ids, lift__project__organization=company,
    ).values_list('id', 'description'))
    result = []
    for row in rows:
        item = {
            'id': row.pk, 'kind': row.kind, 'title': row.title,
            'target_type': row.target_type, 'target_id': row.target_id,
            'created_at': row.created_at, 'read_at': row.read_at,
            'category': 'entrapment' if row.is_entrapment else 'ordinary',
        }
        if row.is_entrapment:
            item['title'] = f'Застревание · заявка №{row.target_id}'
        if row.event_type in ('commissioning_message', 'commissioning_team_chat'):
            item.update(section='chat', preview=(messages.get(row.event_id) or 'Фотографии')[:160])
        elif row.event_type == 'commissioning_progress':
            item.update(section='lifts', preview=progress.get(row.event_id, '')[:160])
        result.append(item)
    return Response({'unread': unread_count, 'results': result, 'unread_by_category': {
        'entrapment': unread_by_category.get(True, 0), 'ordinary': unread_by_category.get(False, 0),
    }},
                    headers={'Cache-Control': 'private, no-store'})



@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def mark_read(request, notification_id):
    item=get_object_or_404(_visible_inbox(request.user, org(request.user)).select_for_update(),
                           pk=notification_id)
    if item.read_at is None:
        item.read_at=timezone.now()
        item.save(update_fields=['read_at'])
    return Response({'ok':True,'id':item.pk,'read_at':item.read_at})
