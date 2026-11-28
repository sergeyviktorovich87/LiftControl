"""A repair requires an explicit workflow decision, never just ticket acceptance."""
from django.db.models import Q
from .models import Ticket, TicketEvent


def repair_events():
    # Keep pre-0.13.47 transfers made by the entrapment release form.
    return TicketEvent.objects.filter(Q(action__in=('repair_requested','stopped','long_repair','resumed')) | Q(
        action='type_changed',before='ENTRAPMENT',after='NORMAL',reason__startswith='Люди освобождены.'))


def in_repair(ticket):
    if ticket.status not in ('NEW','IN_PROGRESS','STOPPED','LONG_REPAIR'):
        return False
    decision=getattr(ticket,'has_repair_decision',None)
    return ticket.status in ('STOPPED','LONG_REPAIR') or (bool(decision) if decision is not None else repair_events().filter(
        ticket=ticket,organization=ticket.organization).exists())


def can_mark_repair(user, ticket):
    from .access import role
    from .ticket_flow import PRIVILEGED, is_on_duty, can_finish_ticket
    return bool(ticket.elevator_id and ticket.priority != Ticket.Priority.ENTRAPMENT
        and ticket.status in ('NEW','IN_PROGRESS') and not in_repair(ticket)
        and (role(user) in PRIVILEGED or is_on_duty(user) or can_finish_ticket(user,ticket)))
