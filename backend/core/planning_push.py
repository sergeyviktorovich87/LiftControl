"""Durable per-device WebPush for vacation decisions and duty publication."""
import json
from datetime import timedelta
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from .access import MemberAccess,org
from .models import PlanningPushDelivery,PushSubscription,NotificationInbox
from .notification_inbox import _visible_inbox
from .commissioning_push import inbox_push_allowed
from .push_notifications import push_config,valid_endpoint

def enqueue(organization,users,event_type,event_id):
    notifications=NotificationInbox.objects.filter(organization=organization,user_id__in=users,event_type=event_type,event_id=event_id)
    subscriptions=list(PushSubscription.objects.filter(organization=organization,user_id__in=users))
    PlanningPushDelivery.objects.bulk_create([PlanningPushDelivery(notification=n,subscription=s) for n in notifications for s in subscriptions if s.user_id==n.user_id],ignore_conflicts=True)

def target(item):
    return f'/?organization={item.organization_id}#'+(f'vacations/request/{item.target_id}' if item.target_type=='vacation' else 'duty')

@api_view(['GET'])
@permission_classes([MemberAccess])
def content(request,pk):
    item=get_object_or_404(_visible_inbox(request.user,org(request.user)),pk=pk,target_type__in=['vacation','duty'])
    return Response({'id':item.pk,'title':item.title,'body':item.body,'url':target(item),'read':bool(item.read_at)},headers={'Cache-Control':'private, no-store'})

def process_batch(limit=20):
    config=push_config()
    if not config['enabled']: return 0
    now=timezone.now()
    with transaction.atomic():
        rows=list(PlanningPushDelivery.objects.select_for_update(skip_locked=True).filter(state='PENDING',next_attempt_at__lte=now).order_by('pk')[:limit])
        for row in rows:
            row.attempts+=1;row.next_attempt_at=now+timedelta(minutes=2)
        PlanningPushDelivery.objects.bulk_update(rows,['attempts','next_attempt_at'])
    from pywebpush import webpush,WebPushException
    for row in rows:
        item=row.notification;sub=row.subscription;user=sub.user;user._organization_id=item.organization_id
        if (not user.is_active or sub.organization_id!=item.organization_id or sub.user_id!=item.user_id or not valid_endpoint(sub.endpoint) or item.created_at<now-timedelta(minutes=30) or not _visible_inbox(user,item.organization).filter(pk=item.pk,read_at__isnull=True).exists() or not inbox_push_allowed(item,now)):
            state='DISABLED'
        else:
            try:
                webpush(subscription_info={'endpoint':sub.endpoint,'keys':{'p256dh':sub.p256dh,'auth':sub.auth}},data=json.dumps({'target':'planning','organization_id':item.organization_id,'inbox_id':item.pk,'event_id':item.pk}),vapid_private_key=config['private_file'],vapid_claims={'sub':config['subject']},ttl=300,timeout=5)
                state='SENT'
            except WebPushException as e:
                if e.status_code in (404,410): sub.delete();continue
                state='FAILED' if row.attempts>=4 else 'PENDING'
            except Exception: state='FAILED' if row.attempts>=4 else 'PENDING'
        PlanningPushDelivery.objects.filter(pk=row.pk).update(state=state,next_attempt_at=now+timedelta(seconds=20*2**row.attempts))
    return len(rows)
