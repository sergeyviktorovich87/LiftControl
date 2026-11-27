"""Recipient names are available only to the sender, managers, or event participants.

All timestamps come from acknowledgments; push-provider acceptance is never delivery.
"""
from django.db.models import Q, Max
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework import serializers
from .access import MemberAccess, org, role, commissioning_access, memberships
from .models import (NotificationInbox, ChatMessage, CommissioningMessage, Ticket,
                     TicketComment, TicketEvent, TicketDeliveryReceipt)
from .notification_inbox import _visible_inbox


class Selection(serializers.Serializer):
    target = serializers.ChoiceField(choices=['chat', 'commissioning_chat', 'ticket_comment', 'ticket', 'commissioning'])
    id = serializers.IntegerField(min_value=1)
    before = serializers.IntegerField(min_value=1, required=False)


class RecipientReader:
    def __init__(self, company, scope):
        self.company = company
        self.rows = list(scope.select_related('user').order_by('user__first_name', 'user__last_name', 'user_id'))
        self.visible = {}
        self.ids = [row.pk for row in self.rows]
        self.dispatch = {(r.event_id, r.recipient_id): r for r in TicketDeliveryReceipt.objects.filter(
            ticket__organization=company, event_id__in=[r.event_id for r in self.rows if r.event_type == 'ticket'])}

    def __call__(self, event_type, event_id):
        result = []
        for row in self.rows:
            if (row.event_type, row.event_id) != (event_type, event_id):
                continue
            user = row.user
            if user.pk not in self.visible:
                user._organization_id = self.company.pk
                self.visible[user.pk] = set(_visible_inbox(user, self.company).filter(pk__in=self.ids).values_list('pk', flat=True)) if user.is_active and memberships(user).filter(organization=self.company).exists() else set()
            if row.pk not in self.visible[user.pk]:
                continue
            item = {'id': user.pk, 'name': user.get_full_name() or user.username,
                    'delivered_at': row.delivered_at, 'read_at': row.message_read_at}
            receipt = self.dispatch.get((event_id, user.pk)) if event_type == 'ticket' else None
            if receipt:
                item['delivered_at'] = item['delivered_at'] or receipt.received_at
                item['read_at'] = item['read_at'] or receipt.read_at
            result.append(item)
        return result


def event_data(reader, row):
    return {'id': row.pk, 'target': 'commissioning_progress' if row.event_type == 'commissioning_progress' else 'commissioning_action',
            'event_id': row.event_id, 'title': row.title, 'body': row.body,
            'created_at': row.created_at, 'recipients': reader(row.event_type, row.event_id)}


@api_view(['GET'])
@permission_classes([MemberAccess])
def details(request):
    form = Selection(data=request.query_params)
    form.is_valid(raise_exception=True)
    target, pk = form.validated_data['target'], form.validated_data['id']
    company, user = org(request.user), request.user
    managing = role(user) in ('ADMIN', 'DIRECTOR', 'DISPATCHER')
    if target == 'commissioning':
        from .commissioning import _project, _manager
        from .models import AuditEvent, CommissioningProgress
        _project(request, pk)
        rows = NotificationInbox.objects.filter(organization=company, target_type='commissioning', target_id=pk,
            event_type__in=['commissioning_progress', 'commissioning_action'])
        if not _manager(user):
            own_actions = AuditEvent.objects.filter(organization=company, actor=user).values('pk')
            own_progress = CommissioningProgress.objects.filter(lift__project_id=pk, actor=user).values('pk')
            visible = _visible_inbox(user, company).values('pk')
            rows = rows.filter(Q(pk__in=visible) | Q(event_type='commissioning_action', event_id__in=own_actions) |
                               Q(event_type='commissioning_progress', event_id__in=own_progress))
        # Group before pagination: one activity may have many recipients.
        groups = rows.values('event_type', 'event_id').annotate(last_id=Max('pk'))
        if 'before' in form.validated_data:
            groups = groups.filter(last_id__lt=form.validated_data['before'])
        groups = list(groups.order_by('-last_id')[:31])
        selected = Q(pk__in=[])
        for g in groups[:30]:
            selected |= Q(event_type=g['event_type'], event_id=g['event_id'])
        reader = RecipientReader(company, NotificationInbox.objects.filter(organization=company).filter(selected))
        events = [event_data(reader, rows.get(pk=g['last_id'])) for g in groups[:30]]
        data = {'events': events, 'next': groups[29]['last_id'] if len(groups) > 30 else None}
    elif target == 'ticket':
        if role(user) == 'ADJUSTER':
            raise NotFound()
        ticket = get_object_or_404(Ticket, organization=company, pk=pk)
        events = TicketEvent.objects.filter(ticket=ticket, organization=company,
            pk__in=NotificationInbox.objects.filter(organization=company, event_type='ticket', target_id=pk).values('event_id')).order_by('-pk')
        reader = RecipientReader(company, NotificationInbox.objects.filter(organization=company, event_type='ticket', target_id=pk))
        data = {'events': [{'id': e.pk, 'title': e.get_action_display() if hasattr(e, 'get_action_display') else {
            'created':'Заявка создана', 'reassigned':'Исполнитель изменён', 'escalated':'Застревание',
            'stopped':'Лифт остановлен', 'long_repair':'Длительный ремонт'}.get(e.action, e.action),
            'created_at': e.created_at, 'recipients': reader('ticket', e.pk)} for e in events],
            'accepted_at': ticket.accepted_at,
            'accepted_by': ticket.assigned_to.full_name if ticket.accepted_at and ticket.assigned_to_id else None}
    else:
        model, event_type = {'chat': (ChatMessage, 'team_chat'), 'commissioning_chat': (CommissioningMessage, 'commissioning_team_chat'),
                             'ticket_comment': (TicketComment, 'ticket_comment')}[target]
        if (target == 'commissioning_chat' and not commissioning_access(user)) or (target != 'commissioning_chat' and role(user) == 'ADJUSTER'):
            raise NotFound()
        message = get_object_or_404(model, organization=company, pk=pk)
        if message.author_id != user.pk and not managing:
            raise NotFound()
        reader = RecipientReader(company, NotificationInbox.objects.filter(organization=company, event_type=event_type, event_id=message.pk))
        data = {'events': [{'id': message.pk, 'title': 'Сообщение', 'created_at': message.created_at,
                           'recipients': reader(event_type, message.pk)}]}
    return Response(data, headers={'Cache-Control': 'private, no-store'})
