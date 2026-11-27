"""Per-device browser push for protected inbox events (existing durable table)."""
import os
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from .access import MemberAccess,org
from .models import PlanningPushDelivery,PushSubscription,NotificationInbox,Ticket,PartRequest
from .notification_inbox import _visible_inbox
from .notification_content import inbox_text
from .commissioning_push import inbox_push_allowed
from .push_notifications import push_config,valid_endpoint
from .webpush_transport import send,retry_delay,confirmation_delay,MAX_ATTEMPTS
import logging
log=logging.getLogger('liftcontrol.push')

def enqueue(organization,users,event_type,event_id):
    notifications=NotificationInbox.objects.filter(organization=organization,user_id__in=users,event_type=event_type,event_id=event_id)
    # A browser belongs to a person, not just their first employer.
    subscriptions=list(PushSubscription.objects.filter(user_id__in=users))
    PlanningPushDelivery.objects.bulk_create([PlanningPushDelivery(notification=n,subscription=s) for n in notifications for s in subscriptions if s.user_id==n.user_id],ignore_conflicts=True)

def target(item):
    base=f'/?organization={item.organization_id}'
    if item.target_type=='vacation':return base+f'#vacations/request/{item.target_id}'
    if item.target_type=='duty':return base+'#duty'
    if item.target_type in ('ticket','ticket_delivery'):return base+f'&ticket={item.target_id}#tickets'
    if item.target_type=='chat':return base+'#chat'
    if item.target_type=='commissioning_chat':return base+'#commissioning-chat'
    if item.target_type=='commissioning':return base+f'#commissioning/project/{item.target_id}'
    if item.target_type=='part':return base+'#parts'
    return base+'#notifications'

def allowed(item,now):
    if item.event_type=='push_test':return True
    if item.event_type=='ticket_comment' or item.target_type=='ticket_delivery':
        from .notification_preferences import ticket_recipients,allows,personal_ticket
        ticket=Ticket.objects.filter(pk=item.target_id,organization_id=item.organization_id).first()
        return bool(ticket and ticket_recipients(ticket,'commented').filter(user_id=item.user_id).exists() and allows(item.user_id,item.organization_id,'updates',personal=lambda:personal_ticket(ticket,item.user_id)))
    if item.target_type=='part':
        from .notification_preferences import allows
        return allows(item.user_id,item.organization_id,'updates',personal=lambda:PartRequest.objects.filter(pk=item.target_id,organization_id=item.organization_id,requested_by_id=item.user_id).exists())
    return inbox_push_allowed(item,now)

@api_view(['GET'])
@permission_classes([MemberAccess])
def content(request,pk):
    item=get_object_or_404(_visible_inbox(request.user,org(request.user)),pk=pk,target_type__in=['vacation','duty'])
    return Response({'id':item.pk,'title':item.title,'body':item.body,'url':target(item),'read':bool(item.read_at)},headers={'Cache-Control':'private, no-store'})

@api_view(['GET'])
@permission_classes([MemberAccess])
def inbox_content(request,pk):
    item=get_object_or_404(_visible_inbox(request.user,org(request.user)),pk=pk)
    return Response({'id':item.pk,'title':item.title,'body':inbox_text(item),'url':target(item),'read':bool(item.read_at)},headers={'Cache-Control':'private, no-store'})

def deliver(row,config):
    item=row.notification;sub=row.subscription;user=sub.user;user._organization_id=item.organization_id;now=timezone.now()
    if (not user.is_active or sub.user_id!=item.user_id or not valid_endpoint(sub.endpoint) or item.created_at<now-timedelta(hours=24) or not _visible_inbox(user,item.organization).filter(pk=item.pk,read_at__isnull=True).exists() or not allowed(item,now)):
        return 'DISABLED'
    from .webpush_health import receipt_token
    payload={'target':'planning' if item.target_type in ('vacation','duty') else 'inbox','organization_id':item.organization_id,'inbox_id':item.pk,'event_id':item.pk,'title':item.title,'body':inbox_text(item),'receipt_token':receipt_token('inbox',row)}
    return send(sub,payload,config,ttl=86400-(now-item.created_at).total_seconds(),urgent=item.is_entrapment)

def process_batch(limit=20, *, parallel=False):
    config=push_config()
    if not config['enabled'] or not config.get('private_file') or not os.path.isfile(config['private_file']):return 0
    now=timezone.now()
    with transaction.atomic():
        rows=list(PlanningPushDelivery.objects.select_for_update(skip_locked=True,of=('self',)).filter(Q(state__in=['PENDING','PROCESSING'])|Q(state='SENT',attempts__lt=3),next_attempt_at__lte=now).select_related('notification','subscription__user').order_by('-notification__created_at','pk')[:limit])
        for row in rows:row.state='PROCESSING';row.attempts+=1;row.next_attempt_at=now+timedelta(minutes=4)
        PlanningPushDelivery.objects.bulk_update(rows,['state','attempts','next_attempt_at'])
    def deliver_claimed(row):
        try:state=deliver(row,config)
        except PushSubscription.DoesNotExist:state='EXPIRED'
        except Exception as exc:log.warning('inbox_webpush_failed delivery=%s error=%s',row.pk,type(exc).__name__);state='RETRY'
        if state=='EXPIRED':return
        if state=='RETRY':state='PENDING' if row.attempts<MAX_ATTEMPTS else 'FAILED'
        PlanningPushDelivery.objects.filter(pk=row.pk,attempts=row.attempts,state='PROCESSING').update(state=state,next_attempt_at=timezone.now()+(timedelta(days=3650) if state not in ('PENDING','SENT') or state=='SENT' and row.attempts>=3 else confirmation_delay(row.attempts) if state=='SENT' else retry_delay(row.attempts)))
    from .push_dispatch import dispatch
    dispatch(rows, deliver_claimed, parallel=parallel)
    return len(rows)
