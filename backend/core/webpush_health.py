"""Scoped push diagnostics and signed display receipts; never exposes endpoints/keys."""
from datetime import timedelta
from django.core import signing
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view,authentication_classes,permission_classes,throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle,UserRateThrottle
from rest_framework.exceptions import ValidationError,PermissionDenied
from .access import MemberAccess,org,memberships,audit
from .models import PushDelivery,PlanningPushDelivery,PushSubscription,NotificationInbox,TicketDeliveryReceipt,PersonalTaskPush
SALT='liftcontrol.webpush.display.v1'

def receipt_token(kind,row):
    sub=row.subscription
    return signing.dumps([kind,row.pk,sub.pk,sub.user_id],salt=SALT,compress=True)

class ReceiptThrottle(AnonRateThrottle):
    rate='20/min'
    scope='webpush_receipt'

    def get_cache_key(self,request,view):
        # A shared office/mobile NAT must not throttle different devices' receipts.
        try:
            kind,pk,sub,user=signing.loads(request.data.get('token',''),salt=SALT,max_age=86400)
            if kind not in ('ticket','task','inbox') or any(type(value) is not int for value in (pk,sub,user)):raise ValueError()
            return self.cache_format % {'scope':self.scope,'ident':f'{kind}:{pk}:{sub}'}
        except (ValueError,TypeError,KeyError,signing.BadSignature):
            return super().get_cache_key(request,view)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ReceiptThrottle])
def received(request):
    try:
        kind,pk,sub,user=signing.loads(request.data.get('token',''),salt=SALT,max_age=86400)
        model={'ticket':PushDelivery,'inbox':PlanningPushDelivery,'task':PersonalTaskPush}[kind]
    except (ValueError,TypeError,KeyError,signing.BadSignature):
        raise ValidationError('Недействительное подтверждение push.')
    row=get_object_or_404(model.objects.select_related('subscription__user'),pk=pk,subscription_id=sub,subscription__user_id=user)
    company=row.organization_id if kind=='ticket' else row.event.task.organization_id if kind=='task' else row.notification.organization_id
    if not row.subscription.user.is_active or not memberships(row.subscription.user).filter(organization_id=company).exists():
        raise PermissionDenied('Доступ к организации прекращён.')
    model.objects.filter(pk=pk).update(state='DISPLAYED',next_attempt_at=timezone.now()+timedelta(days=3650))
    if kind=='ticket':
        event=row.ticket.events.filter(action=row.kind,created_at__lte=row.created_at).order_by('-pk').first()
        if event:TicketDeliveryReceipt.objects.filter(ticket_id=row.ticket_id,event=event,recipient_id=user,received_at__isnull=True).update(received_at=timezone.now())
    return Response({'ok':True})

def queue_status(user,company):
    since=timezone.now()-timedelta(hours=24)
    tickets=PushDelivery.objects.filter(organization=company,subscription__user=user,created_at__gte=since)
    inbox=PlanningPushDelivery.objects.filter(notification__organization=company,subscription__user=user,notification__created_at__gte=since)
    counts={}
    tasks=PersonalTaskPush.objects.filter(event__task__organization=company,subscription__user=user,created_at__gte=since)
    for query in (tickets,inbox,tasks):
        for row in query.values('state').annotate(count=Count('pk')):counts[row['state']]=counts.get(row['state'],0)+row['count']
    return {'devices':PushSubscription.objects.filter(user=user).count(),'last_24h':counts,'accepted_note':'SENT — принято push-провайдером; DISPLAYED — браузер подтвердил showNotification.'}

@api_view(['GET'])
@permission_classes([MemberAccess])
def status(request):
    return Response(queue_status(request.user,org(request.user)),headers={'Cache-Control':'private, no-store'})

class ProbeThrottle(UserRateThrottle):
    rate='4/min'
    scope='webpush_probe'

@api_view(['POST'])
@permission_classes([MemberAccess])
@throttle_classes([ProbeThrottle])
@transaction.atomic
def test_push(request):
    from .notification_inbox import _enqueue
    if not PushSubscription.objects.filter(user=request.user).exists():raise ValidationError('Сначала подключите уведомления на устройстве.')
    subs=PushSubscription.objects.filter(user=request.user)
    endpoint=request.data.get('endpoint')
    sub=get_object_or_404(subs,endpoint=endpoint) if endpoint else subs.first()
    previous=PlanningPushDelivery.objects.filter(subscription=sub,notification__organization=org(request.user),notification__event_type='push_test',notification__created_at__gte=timezone.now()-timedelta(seconds=15)).select_related('notification').order_by('-pk').first()
    recent=previous.notification if previous else None
    if not recent:
        event=audit(request.user,'push.test','self')
        _enqueue(org(request.user),[request.user.pk],'push_test',event.pk,'test','Проверка доставки с сервера','push_test',event.pk,push=True,body='Это уведомление прошло серверную очередь и браузерный push-канал.')
        recent=NotificationInbox.objects.get(organization=org(request.user),user=request.user,event_type='push_test',event_id=event.pk)
        PlanningPushDelivery.objects.filter(notification=recent).exclude(subscription=sub).delete()
    return Response({'id':recent.pk},status=202)

@api_view(['GET'])
@permission_classes([MemberAccess])
def test_status(request,pk):
    row=get_object_or_404(NotificationInbox,pk=pk,user=request.user,organization=org(request.user),event_type='push_test')
    return Response({'id':row.pk,'states':list(PlanningPushDelivery.objects.filter(notification=row).values_list('state',flat=True))},headers={'Cache-Control':'private, no-store'})
