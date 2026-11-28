"""Current repair work and repeated calls. No invented links for house-only calls."""
from datetime import timedelta
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .access import MemberAccess, org
from .models import Elevator, Ticket


def current_lifts(company):
    return Elevator.objects.filter(organization=company, active=True, deleted_at__isnull=True,
        building__organization=company, building__deleted_at__isnull=True).select_related('building')


def recent(company, now):
    return Ticket.objects.filter(organization=company, elevator__in=current_lifts(company),
        created_at__gte=now-timedelta(days=7), created_at__lte=now).exclude(status='CANCELED')


def lift_data(lift):
    return {'id':lift.pk, 'address':lift.building.address, 'entrance':lift.entrance,
            'entrance_kind':lift.entrance_kind, 'number':lift.display_number}


@api_view(['GET'])
@permission_classes([MemberAccess])
def condition(request):
    company, now = org(request.user), timezone.now()
    lifts = {lift.pk:lift for lift in current_lifts(company)}
    work = Ticket.objects.filter(organization=company, elevator_id__in=lifts).filter(Q(status__in=['IN_PROGRESS','STOPPED','LONG_REPAIR']) | Q(
            status='NEW', events__action='type_changed', events__before='ENTRAPMENT', events__after='NORMAL'
        )).exclude(priority='ENTRAPMENT').distinct().order_by('-updated_at','-pk')
    ranks = {'LONG_REPAIR':0,'STOPPED':1,'IN_PROGRESS':2,'NEW':3}
    chosen = {}
    for ticket in work:
        previous = chosen.get(ticket.elevator_id)
        if previous is None or ranks[ticket.status] < ranks[previous.status]:
            chosen[ticket.elevator_id] = ticket
    repairs = []
    for lift in lifts.values():
        ticket = chosen.get(lift.pk)
        if ticket is None and lift.stopped_at is None:
            continue
        from .ticket_flow import current_ticket_title
        repairs.append({**lift_data(lift), 'ticket_id':ticket.pk if ticket else None,
            'status':ticket.status if ticket else 'STOPPED',
            'reason':(ticket.long_repair_reason or ticket.stop_reason or current_ticket_title(ticket)) if ticket else lift.stop_reason,
            'since':(ticket.stopped_at or ticket.accepted_at or ticket.created_at) if ticket else lift.stopped_at})
    attention = [{**lift_data(lifts[row['elevator_id']]), 'count':row['count'], 'latest_at':row['latest_at']}
        for row in recent(company, now).filter(elevator_id__in=lifts).values('elevator_id').annotate(count=Count('pk'), latest_at=Max('created_at'))
        .filter(count__gte=6).order_by('-count','-latest_at','elevator_id')]
    return Response({'repairs':repairs, 'attention':attention, 'since':now-timedelta(days=7), 'through':now},
        headers={'Cache-Control':'private, no-store'})


@api_view(['GET'])
@permission_classes([MemberAccess])
def attention_tickets(request, pk):
    company, now = org(request.user), timezone.now()
    lift = get_object_or_404(current_lifts(company), pk=pk)
    from .serializers import TicketSerializer
    rows = recent(company, now).filter(elevator=lift).order_by('-created_at','-pk')
    return Response({'lift':lift_data(lift), 'since':now-timedelta(days=7), 'tickets':TicketSerializer(rows,many=True,context={'request':request}).data},
        headers={'Cache-Control':'private, no-store'})
