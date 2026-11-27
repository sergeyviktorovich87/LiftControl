"""Server-owned notification history.

Inbox records are not delivery acknowledgments, and marking as read must
never accept a ticket or task. Push transports can fail independently of this
history; privacy is enforced at creation and again at read time.
"""
from .notification_content import inbox_text

from django.db import transaction
from django.db.models import Case, Count, F, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.serializers import BooleanField, ChoiceField, IntegerField, Serializer

from .access import MemberAccess, org, role, technician_id, commissioning_access
from .models import Membership, NotificationInbox, CommissioningAssignment, CommissioningMessage, CommissioningProgress, PersonalTask
from .models import InspectionReminder

QUIET_TICKET_EVENTS = ('accepted', 'completed', 'resumed')
IMPORTANT_TICKET_EVENTS = ('created', 'reassigned', 'escalated')
TICKET_TITLES = {
    'created': 'Новая заявка',
    'reassigned': 'Назначен механик',
    'canceled': 'Заявка отменена',
    'stopped': 'Лифт остановлен',
    'long_repair': 'Длительный ремонт',
}
TASK_TITLES = {
    'created': 'Новое задание', 'assigned': 'Назначено задание',
    'accepted': 'Задание принято', 'completed': 'Задание выполнено',
    'canceled': 'Задание отменено',
}


SECTION_BY_TARGET = {
    'vacation':'vacations', 'duty':'duty',
    'ticket': 'tickets', 'task': 'tasks', 'commissioning': 'commissioning',
    'commissioning_chat': 'commissioning', 'part': 'parts', 'chat': 'chat',
    'inspection': 'elevators', 'ticket_delivery': 'tickets',
}


def _enqueue(organization, user_ids, event_type, event_id, kind, title,
             target_type, target_id, *, push=False, is_entrapment=False, body=''):
    unique={int(uid) for uid in user_ids if uid}
    NotificationInbox.objects.bulk_create([
        NotificationInbox(organization=organization, user_id=uid,
                          event_type=event_type, event_id=event_id,
                          kind=kind, title=title[:200], body=body,
                          target_type=target_type, target_id=target_id,
                          is_entrapment=is_entrapment,
                          commissioning_push_after=timezone.now() if push else None)
        for uid in unique
    ], ignore_conflicts=True)
    if target_type in ('vacation','duty','chat','commissioning','commissioning_chat','inspection','ticket_delivery','part','push_test') or event_type=='ticket_comment':
        from .planning_push import enqueue
        enqueue(organization, unique, event_type, event_id)


def enqueue_ticket(event):
    from .notification_preferences import ticket_recipients
    if event.action in QUIET_TICKET_EVENTS:
        return
    ticket = event.ticket
    users = ticket_recipients(ticket, event.action).values_list('user_id', flat=True)
    _enqueue(ticket.organization, users, 'ticket', event.pk, event.action,
             f'{TICKET_TITLES.get(event.action, "Заявка")} №{ticket.pk}', 'ticket', ticket.pk,
             is_entrapment=ticket.priority == 'ENTRAPMENT' and event.action in IMPORTANT_TICKET_EVENTS)


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
             f'{TASK_TITLES.get(event.action, "Личное задание")} №{task.pk}','task',task.pk)


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


def enqueue_commissioning_progress(event):
    project = event.lift.project
    users = _commissioning_recipients(project, event.actor_id, lift_id=event.lift_id)
    _enqueue(project.organization, users, 'commissioning_progress', event.pk, 'progress',
             f'Комментарий по наладке: {project.name} · {event.lift.label}',
             'commissioning', project.pk, push=True, body=getattr(event, 'description', '') or '')


def enqueue_commissioning_action(project, event, kind, title, *, recipient=None):
    from .models import CommissioningExpense, CommissioningNeed, CommissioningExtraWork, CommissioningLiftRequest
    model = (CommissioningExpense if kind.startswith('expense_') else
             CommissioningNeed if kind.startswith('need_') else
             CommissioningExtraWork if kind.startswith('extra_') else
             CommissioningLiftRequest if kind in ('lift_requested', 'lift_decided') else None)
    item = model.objects.filter(pk=event.object_id, project=project).first() if model else None
    body = getattr(item, 'description', '') or getattr(item, 'label', '')
    if isinstance(item, CommissioningExpense):
        body = f'{item.amount} ₽ · {item.spent_on}\n{body}'

    if recipient is None:
        users = Membership.objects.filter(
            organization=project.organization, active=True, user__is_active=True,
            role__in=('ADMIN', 'DIRECTOR'),
        ).exclude(user_id=event.actor_id).values_list('user_id', flat=True)
    else:
        users = [] if recipient == event.actor_id else [recipient]
    _enqueue(project.organization, users, 'commissioning_action', event.pk, kind,
             f'{title} · {project.name}', 'commissioning', project.pk, push=True, body=body)


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
             'Новое сообщение в чате наладчиков', 'commissioning_chat', message.pk, push=True, body=message.text)


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
             'Новое сообщение в чате команды','chat',message.pk, push=True, body=message.body)

def _visible_inbox(user, company):
    # An already-created inbox row is not a permanent access grant.
    rows = NotificationInbox.objects.filter(user=user, organization=company).exclude(
        event_type='commissioning_message',
    ).exclude(event_type='ticket', kind__in=QUIET_TICKET_EVENTS)
    current_role = role(user)
    if current_role not in ('ADMIN','DIRECTOR'):
        from .models import VacationRequest
        own = VacationRequest.objects.filter(organization=company,employee=user).values('pk')
        rows = rows.filter(~Q(target_type='vacation')|Q(target_id__in=own))
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
                           Q(target_type='commissioning_chat') | Q(target_type='vacation') | Q(target_type='push_test'))
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


def with_category(rows):
    return rows.annotate(important=Case(
        When(is_entrapment=True, kind__in=IMPORTANT_TICKET_EVENTS, then=Value(True)),
        default=Value(False),
    ))


@api_view(['GET'])
@permission_classes([MemberAccess])
def revision(request):
    """Only the newest visible event ID; no message text or foreign scope."""
    latest = _visible_inbox(request.user, org(request.user)).order_by('-pk').values_list('pk', flat=True).first() or 0
    return Response({'revision': str(latest)}, headers={'Cache-Control': 'private, no-store'})


@api_view(['GET'])
@permission_classes([MemberAccess])
def counts(request):
    unread = with_category(_visible_inbox(request.user, org(request.user))).filter(read_at__isnull=True)
    sections = {section: 0 for section in SECTION_BY_TARGET.values()}
    total = entrapment = chat = 0
    for row in unread.order_by().values('target_type', 'important').annotate(count=Count('pk')):
        target, count = row['target_type'], row['count']
        total += count
        if row['important']:
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


class OpenedPush(Serializer):
    target = ChoiceField(choices=['ticket', 'ticket_comment', 'chat', 'task', 'commissioning', 'commissioning_chat', 'inspection', 'ticket_delivery'])
    target_id = IntegerField(min_value=1, max_value=2**63 - 1)
    event_id = IntegerField(min_value=1, max_value=2**63 - 1)


@api_view(['POST'])
@permission_classes([MemberAccess])
def read_push(request):
    validated = OpenedPush(data=request.data)
    validated.is_valid(raise_exception=True)
    data = validated.validated_data
    target = data['target']
    # Ticket/task pushes identify the business event. Commissioning and
    # inspection pushes carry the recipient's inbox record ID.
    event = ({'event_type': target, 'event_id': data['event_id']}
             if target in ('ticket', 'task') else {'pk': data['event_id']})
    updated = _visible_inbox(request.user, org(request.user)).filter(
        target_type='ticket' if target == 'ticket_comment' else target, target_id=data['target_id'], read_at__isnull=True, **event,
    ).update(read_at=timezone.now())
    return Response({'updated': updated})


@api_view(['GET'])
@permission_classes([MemberAccess])
def inbox(request):
    company=org(request.user)
    visible = with_category(_visible_inbox(request.user, company))
    category = request.query_params.get('category')
    if category not in (None, 'ordinary', 'entrapment', 'commissioning'):
        raise ValidationError({'category': 'Укажите обычные, важные или уведомления наладки.'})
    commissioning = Q(target_type__in=('commissioning', 'commissioning_chat'))
    separate = request.query_params.get('group_commissioning') == '1' or category == 'commissioning'
    category_filters = {
        'entrapment': Q(important=True),
        'ordinary': Q(important=False) & (~commissioning if separate else Q()),
        'commissioning': commissioning,
    }
    unread_by_category = {
        name: visible.filter(rule, read_at__isnull=True).count()
        for name, rule in category_filters.items() if separate or name != 'commissioning'
    }
    if category is not None:
        visible = visible.filter(category_filters[category])
    unread_count = sum(unread_by_category.values()) if category is None else unread_by_category.get(category, 0)
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
    before = request.query_params.get('before')
    if before is not None:
        boundary = IntegerField(min_value=1, max_value=2**63 - 1).run_validation(before)
        visible = visible.filter(pk__lt=boundary)
    rows = list(visible.order_by('-pk')[:limit + 1])
    next_before = rows[limit - 1].pk if len(rows) > limit else None
    rows = rows[:limit]
    message_ids = [row.event_id for row in rows
                   if row.event_type == 'commissioning_team_chat']
    progress_ids = [row.event_id for row in rows if row.event_type == 'commissioning_progress']
    messages = dict(CommissioningMessage.objects.filter(
        organization=company, pk__in=message_ids,
    ).values_list('id', 'text'))
    progress = dict(CommissioningProgress.objects.filter(
        pk__in=progress_ids, lift__project__organization=company,
    ).values_list('id', 'description'))
    result = []
    for row in rows:
        item = {
            'id': row.pk, 'kind': row.kind, 'title': row.title,
            'body': inbox_text(row),
            'target_type': row.target_type, 'target_id': row.target_id,
            'created_at': row.created_at, 'read_at': row.read_at,
            'category': ('commissioning' if separate and row.target_type in ('commissioning', 'commissioning_chat')
                         else 'entrapment' if row.important else 'ordinary'),
        }
        if row.important:
            item['title'] = f'Застревание · заявка №{row.target_id}'
        elif row.event_type == 'ticket':
            item['title'] = f'{TICKET_TITLES.get(row.kind, "Заявка")} №{row.target_id}'
        elif row.event_type == 'task':
            item['title'] = f'{TASK_TITLES.get(row.kind, "Личное задание")} №{row.target_id}'
        if row.event_type == 'commissioning_team_chat':
            item.update(section='chat', preview=messages.get(row.event_id) or 'Фотографии')
        elif row.event_type == 'commissioning_progress':
            item.update(section='lifts', preview=progress.get(row.event_id, ''))
        result.append(item)
    return Response({'unread': unread_count, 'results': result, 'next_before': next_before,
                     'unread_by_category': unread_by_category},
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


@api_view(['GET'])
@permission_classes([MemberAccess])
def sound_events(request):
    """Content-free foreground signals, scoped and filtered like push delivery.

    Bootstrap skips history; advance over muted/read rows too so they never replay.
    """
    from datetime import timedelta
    from .notification_preferences import allows, category, personal_ticket
    from .commissioning_push import inbox_push_allowed, INBOX_PUSH_TARGET_KEYS
    from .models import TicketEvent
    rows = _visible_inbox(request.user, org(request.user)).filter(target_type__in=(*INBOX_PUSH_TARGET_KEYS, 'task'))
    raw = request.query_params.get('after')
    if raw is None:
        cursor = rows.order_by('-pk').values_list('pk', flat=True).first() or 0
        return Response({'after': cursor, 'events': []}, headers={'Cache-Control': 'private, no-store'})
    try:
        after = int(raw)
        if after < 0 or after > 2**63-1:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError('Некорректный указатель уведомлений.')
    batch = list(rows.filter(pk__gt=after).order_by('pk')[:50])
    now = timezone.now()
    events = []
    for item in batch:
        if item.read_at or item.created_at < now-timedelta(minutes=2):
            continue
        if item.target_type == 'ticket' and item.event_type == 'ticket':
            event = TicketEvent.objects.select_related('ticket').filter(pk=item.event_id, organization_id=item.organization_id).first()
            if not event:
                continue
            from .notification_preferences import ticket_recipients
            if not ticket_recipients(event.ticket, event.action).filter(user=request.user).exists():
                continue
            allowed = allows(item.user_id, item.organization_id, category(event.ticket.priority, event.action),
                             personal=lambda: personal_ticket(event.ticket, item.user_id), now=now)
        elif item.target_type == 'task':
            allowed = allows(item.user_id, item.organization_id, 'tasks', now=now)
        else:
            allowed = inbox_push_allowed(item, now)
        if allowed:
            events.append({'id': item.pk, 'important': item.is_entrapment})
    return Response({'after': batch[-1].pk if batch else after, 'events': events},
                    headers={'Cache-Control': 'private, no-store'})
