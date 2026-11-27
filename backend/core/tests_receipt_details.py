from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from .tests_message_receipts import MessageReceiptTests
from .models import (Membership, NotificationInbox, Technician, Building, Elevator, DutyShift,
                     CommissioningProject, CommissioningLift, CommissioningAssignment,
                     CommissioningProgress, AuditEvent)
from .notification_inbox import enqueue_commissioning_progress, enqueue_commissioning_action


class ReceiptDetailsTests(TestCase):
    setUp = MessageReceiptTests.setUp

    def details(self, target='chat', pk=None, **extra):
        return self.client.get('/api/notifications/receipts/details/',
            {'target':target, 'id':pk or self.message.pk, **extra}, HTTP_X_ORGANIZATION_ID=str(self.org.pk))

    def test_names_timestamps_and_bulk_read_are_separate(self):
        self.row.delivered_at = timezone.now()
        self.row.read_at = timezone.now()
        self.row.save()
        self.client.force_authenticate(self.sender)
        result = self.details()
        self.assertEqual(result.status_code, 200, result.data)
        person = result.data['events'][0]['recipients'][0]
        self.assertEqual((person['id'], person['name']), (self.recipient.pk, 'recipient'))
        self.assertIsNotNone(person['delivered_at'])
        self.assertIsNone(person['read_at'])
        self.row.message_read_at = timezone.now(); self.row.save()
        self.assertIsNotNone(self.details().data['events'][0]['recipients'][0]['read_at'])
        self.assertIn('no-store', result['Cache-Control'])

    def test_current_membership_and_tenant_and_sender_privacy(self):
        Membership.objects.filter(user=self.sender).update(role='DISPATCHER')
        self.client.force_authenticate(self.sender)
        self.member.active = False; self.member.save()
        self.assertEqual(self.details().data['events'][0]['recipients'], [])
        self.assertEqual(self.details(pk=999999).status_code, 404)
        from .models import ChatMessage
        foreign=ChatMessage.objects.create(organization=self.other,author=self.sender,body='Другой арендатор')
        self.assertEqual(self.details(pk=foreign.pk).status_code,404)
        Membership.objects.filter(user=self.sender).update(role='ADJUSTER', can_commissioning=True)
        self.assertEqual(self.details().status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.details().status_code, (401,403))

    def test_commissioning_activity_pagination_and_no_read_on_get(self):
        project = CommissioningProject.objects.create(organization=self.org, name='Объект', address='Адрес')
        lift = CommissioningLift.objects.create(project=project, label='Лифт')
        self.member.role = 'ADJUSTER'; self.member.can_commissioning = True; self.member.save()
        CommissioningAssignment.objects.create(lift=lift, user=self.recipient)
        for i in range(32):
            progress = CommissioningProgress.objects.create(lift=lift, actor=self.recipient, before=0, after=1, description=f'Отчёт {i}')
            enqueue_commissioning_progress(progress)
        self.client.force_authenticate(self.sender)
        result = self.details('commissioning', project.pk)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(len(result.data['events']), 30)
        more = self.details('commissioning', project.pk, before=result.data['next'])
        self.assertEqual(len(more.data['events']), 2)
        self.assertFalse(set(e['event_id'] for e in result.data['events']) & set(e['event_id'] for e in more.data['events']))
        self.assertFalse(NotificationInbox.objects.filter(event_type='commissioning_progress', message_read_at__isnull=False).exists())
        event_id = result.data['events'][0]['event_id']
        ack = self.client.post('/api/notifications/receipts/', {'target':'commissioning_progress','ids':[event_id],'read':True},format='json')
        self.assertEqual(ack.status_code,200)
        self.assertIsNotNone(NotificationInbox.objects.get(event_type='commissioning_progress',event_id=event_id,user=self.sender).message_read_at)
        # Revoking the object assignment immediately hides its activity.
        self.client.force_authenticate(self.recipient)
        CommissioningAssignment.objects.update(active=False)
        self.assertEqual(self.details('commissioning', project.pk).status_code,403)

    def test_commissioning_private_action_not_visible_to_other_adjuster(self):
        project = CommissioningProject.objects.create(organization=self.org,name='Объект',address='Адрес')
        lift = CommissioningLift.objects.create(project=project,label='Лифт')
        self.member.role='ADJUSTER'; self.member.can_commissioning=True; self.member.save()
        CommissioningAssignment.objects.create(lift=lift,user=self.recipient)
        event=AuditEvent.objects.create(organization=self.org,actor=self.sender,action='commissioning.expense_created',object_id='123')
        enqueue_commissioning_action(project,event,'expense_created','Личный расход')
        self.client.force_authenticate(self.recipient)
        self.assertEqual(self.details('commissioning',project.pk).data['events'],[])

    def test_entrapment_default_is_current_valid_duty_not_lift_mechanic(self):
        from .ticket_flow import create_ticket
        self.sender._organization_id=self.org.pk
        regular=Technician.objects.create(organization=self.org,full_name='Механик дома')
        duty=Technician.objects.create(organization=self.org,full_name='Дежурный')
        self.member.role='MECHANIC';self.member.technician=duty;self.member.save()
        building=Building.objects.create(organization=self.org,name='Дом',address='Адрес')
        lift=Elevator.objects.create(organization=self.org,building=building,assigned_technician=regular)
        now=timezone.now()
        DutyShift.objects.create(organization=self.org,technician=duty,start=now-timedelta(hours=1),end=now+timedelta(hours=1))
        values={'elevator':lift,'title':'Застревание','priority':'ENTRAPMENT'}
        ticket=create_ticket(self.sender, values)
        self.assertEqual(ticket.assigned_to_id,duty.pk)
        self.client.force_authenticate(self.sender)
        result=self.details('ticket',ticket.pk)
        self.assertEqual(result.data['events'][0]['recipients'][0]['name'],'recipient')
        self.client.force_authenticate(self.recipient)
        self.client.post('/api/notifications/receipts/',{'target':'ticket','ids':[ticket.pk],'read':True},format='json')
        ticket.refresh_from_db();self.assertEqual(ticket.status,'NEW')
        self.client.force_authenticate(self.sender)
        self.assertIsNotNone(self.details('ticket',ticket.pk).data['events'][0]['recipients'][0]['read_at'])
        # Explicit assignee remains possible and the exact boundary excludes an ended shift.
        self.assertEqual(create_ticket(self.sender,{**values,'assigned_to':duty}).assigned_to_id,duty.pk)
        DutyShift.objects.update(end=now-timedelta(seconds=1))
        unassigned=create_ticket(self.sender,values)
        self.assertIsNone(unassigned.assigned_to_id)
        self.assertIsNone(unassigned.responsible_id)
        self.assertEqual(create_ticket(self.sender,{'building':building,'title':'Застревание без лифта','priority':'ENTRAPMENT'}).assigned_to_id,None)

    def test_signed_display_confirms_delivery_without_reading_and_keeps_first_time(self):
        from .models import PushSubscription, PlanningPushDelivery
        from .webpush_health import receipt_token
        sub = PushSubscription.objects.create(organization=self.org,user=self.recipient,
            endpoint='https://fcm.googleapis.com/fcm/send/test-receipt',p256dh='key',auth='key')
        delivery=PlanningPushDelivery.objects.create(notification=self.row,subscription=sub)
        token=receipt_token('inbox',delivery)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/push/received/',{'token':token},format='json').status_code,200)
        self.row.refresh_from_db();first=self.row.delivered_at
        self.assertIsNotNone(first);self.assertIsNone(self.row.message_read_at);self.assertIsNone(self.row.read_at)
        self.client.post('/api/push/received/',{'token':token},format='json')
        self.row.refresh_from_db();self.assertEqual(self.row.delivered_at,first)
        self.assertEqual(self.client.post('/api/push/received/',{'token':token+'broken'},format='json').status_code,400)
