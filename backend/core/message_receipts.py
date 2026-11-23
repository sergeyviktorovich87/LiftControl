"""Per-recipient acknowledgments; a successful send is not a delivery receipt."""
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .access import MemberAccess, org
from .models import NotificationInbox, TicketDeliveryReceipt
from .notification_inbox import _visible_inbox

EVENTS = {'chat': 'team_chat', 'commissioning_chat': 'commissioning_team_chat',
          'ticket_comment': 'ticket_comment'}


def summaries(company, event_type, ids):
    rows = NotificationInbox.objects.filter(organization=company, event_type=event_type,
                                             event_id__in=ids)
    # Removed memberships do not count as current recipients.
    rows = rows.filter(user__is_active=True, user__memberships__organization=company,
                       user__memberships__active=True)
    result = {}
    for row in rows.values('event_id').annotate(
            total=Count('pk', distinct=True),
            delivered=Count('pk', filter=Q(delivered_at__isnull=False) | Q(message_read_at__isnull=False), distinct=True),
            read=Count('pk', filter=Q(message_read_at__isnull=False), distinct=True)):
        result[row['event_id']] = {key: row[key] for key in ('total', 'delivered', 'read')}
    return result


class Acknowledgment(serializers.Serializer):
    target = serializers.ChoiceField(choices=[*EVENTS, 'ticket'])
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=200,
                                allow_empty=False)
    read = serializers.BooleanField(default=False)


@api_view(['POST'])
@permission_classes([MemberAccess])
def acknowledge(request):
    form = Acknowledgment(data=request.data)
    form.is_valid(raise_exception=True)
    data, now = form.validated_data, timezone.now()
    if data['target'] == 'ticket':
        rows = TicketDeliveryReceipt.objects.filter(
            recipient=request.user, ticket__organization=org(request.user), ticket_id__in=data['ids'])
        # Receipt belongs only to the active dispatch and the currently assigned mechanic.
        from .access import technician_id, role
        from .ticket_delivery import DISPATCH
        if role(request.user) != 'MECHANIC':
            return Response({'updated': 0})
        rows = rows.filter(Q(ticket__assigned_to_id=technician_id(request.user)) |
                          Q(ticket__assigned_to__isnull=True,
                            ticket__elevator__assigned_technician_id=technician_id(request.user)))
        ids = [row.pk for row in rows.select_related('ticket')
               if row.event_id == row.ticket.events.filter(action__in=DISPATCH)
               .order_by('-pk').values_list('pk', flat=True).first()]
        rows = TicketDeliveryReceipt.objects.filter(pk__in=ids)
        rows.filter(received_at__isnull=True).update(received_at=now, warn_after=None)
        updated = rows.filter(read_at__isnull=True).update(read_at=now) if data['read'] else len(ids)
    else:
        rows = _visible_inbox(request.user, org(request.user)).filter(
            event_type=EVENTS[data['target']], event_id__in=data['ids'])
        rows.filter(delivered_at__isnull=True).update(delivered_at=now)
        updated = rows.filter(message_read_at__isnull=True).update(message_read_at=now, read_at=now) if data['read'] else rows.count()
    return Response({'updated': updated}, headers={'Cache-Control': 'private, no-store'})
