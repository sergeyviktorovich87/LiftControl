import io
import json
import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Organization,Membership,Technician,Building,Elevator,PushSubscription,PushDelivery,PlanningPushDelivery,Ticket,TicketEvent,NotificationInbox,TicketDeliveryReceipt,ChatMessage,CommissioningMessage,NotificationPreference
from .push_notifications import deliver_one,process_batch
from .webpush_health import receipt_token

class PushReliabilityTests(TestCase):
    def setUp(self):
        self.company=Organization.objects.get(pk=1);self.tech=Technician.objects.create(full_name='Механик');self.admin=self.user('admin','ADMIN');self.worker=self.user('worker','MECHANIC',self.tech)
        home=Building.objects.create(name='Дом',address='Тестовый адрес');self.lift=Elevator.objects.create(building=home,factory_number='PUSH-1',assigned_technician=self.tech)
        self.sub=PushSubscription.objects.create(organization=self.company,user=self.worker,endpoint='https://fcm.googleapis.com/fcm/send/private-endpoint',p256dh='test-key',auth='test-auth')
        self.file=tempfile.NamedTemporaryFile();self.addCleanup(self.file.close);self.config={'enabled':True,'private_file':self.file.name,'public_key':'public-test','subject':'mailto:test@example.com'}
        self.client=APIClient();self.client.force_authenticate(self.admin)
    def user(self,name,role,tech=None):
        user=get_user_model().objects.create_user(username=name,password='long-test-password');Membership.objects.create(user=user,organization=self.company,role=role,technician=tech);return user
    def ticket(self):
        result=self.client.post('/api/tickets/',{'elevator':self.lift.pk,'title':'Проверка','description':'Описание'},format='json');self.assertEqual(result.status_code,201,result.data);return Ticket.objects.get(pk=result.data['id'])
    def test_positive_ticket_delivery_uses_real_event_and_bounded_payload(self):
        ticket=self.ticket();ticket.description='Я'*5000;ticket.save();row=PushDelivery.objects.get(ticket=ticket)
        with patch('pywebpush.webpush') as transport:
            self.assertEqual(deliver_one(row,self.config),'SENT')
        payload=json.loads(transport.call_args.kwargs['data']);self.assertIn('receipt_token',payload);self.assertIn('Тестовый адрес',payload['body']);self.assertLessEqual(len(transport.call_args.kwargs['data'].encode('utf8')),3000);self.assertGreater(transport.call_args.kwargs['ttl'],300)
    def test_poisoned_row_does_not_starve_other_ticket_and_recovers_lease(self):
        first=self.ticket();second=self.ticket();calls=[]
        def send(row,config):
            calls.append(row.ticket_id)
            if row.ticket_id==first.pk:raise RuntimeError('do-not-log-secret-endpoint')
            return 'SENT'
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one',side_effect=send):
            self.assertEqual(process_batch(),2)
        self.assertEqual(len(calls),2);self.assertEqual(PushDelivery.objects.get(ticket=first).state,'PENDING');self.assertEqual(PushDelivery.objects.get(ticket=second).state,'SENT')
        row=PushDelivery.objects.get(ticket=first);row.state='PROCESSING';row.next_attempt_at=timezone.now()-timedelta(seconds=1);row.save()
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one',return_value='SENT'):
            process_batch()
        row.refresh_from_db();self.assertEqual(row.state,'SENT')
    def test_worker_isolates_queues(self):
        module='core.management.commands.run_push_worker.'
        with patch(module+'push_config',return_value={'enabled':True}),patch(module+'enabled',return_value=False),patch(module+'process_batch',side_effect=RuntimeError('secret')),patch(module+'process_planning_batch') as planning,patch(module+'process_native_batch'),patch(module+'process_task_batch') as tasks,patch(module+'process_commissioning_batch'),patch(module+'process_update_batch'):
            output=io.StringIO();errors=io.StringIO();call_command('run_push_worker',once=True,stdout=output,stderr=errors);planning.assert_called_once();tasks.assert_called_once();self.assertIn('channel=tickets',errors.getvalue());self.assertNotIn('secret',errors.getvalue())
    def test_general_chat_has_web_outbox_and_cross_employer_adjuster_receives(self):
        from .notification_inbox import enqueue_team_chat,enqueue_commissioning_chat
        from .planning_push import deliver
        chat=ChatMessage.objects.create(organization=self.company,author=self.admin,body='Сообщение');enqueue_team_chat(chat)
        row=PlanningPushDelivery.objects.get(notification__target_type='chat');self.assertEqual(row.subscription,self.sub)
        with patch('pywebpush.webpush') as send:self.assertEqual(deliver(row,self.config),'SENT')
        self.assertEqual(json.loads(send.call_args.kwargs['data'])['target'],'inbox')
        other=Organization.objects.create(name='Второй работодатель');Membership.objects.create(organization=other,user=self.worker,role='ADJUSTER',can_commissioning=True)
        message=CommissioningMessage.objects.create(organization=other,author=self.admin,text='Сообщение наладки');enqueue_commissioning_chat(message)
        row=PlanningPushDelivery.objects.get(notification__target_type='commissioning_chat');self.assertEqual(row.subscription.organization_id,self.company.pk)
        with patch('pywebpush.webpush'):self.assertEqual(deliver(row,self.config),'SENT')
        Membership.objects.filter(organization=other,user=self.worker).update(active=False)
        with patch('pywebpush.webpush') as send:self.assertEqual(deliver(row,self.config),'DISABLED');send.assert_not_called()
    def test_display_receipt_is_signed_does_not_accept_or_mark_read(self):
        ticket=self.ticket();row=PushDelivery.objects.get(ticket=ticket);token=receipt_token('ticket',row)
        self.client.force_authenticate(None);response=self.client.post('/api/push/received/',{'token':token},format='json');self.assertEqual(response.status_code,200,response.data)
        row.refresh_from_db();ticket.refresh_from_db();self.assertEqual(row.state,'DISPLAYED');self.assertEqual(ticket.status,'NEW')
        receipt=TicketDeliveryReceipt.objects.get(ticket=ticket,recipient=self.worker);self.assertIsNotNone(receipt.received_at);self.assertIsNone(receipt.read_at)
        self.assertEqual(self.client.post('/api/push/received/',{'token':token+'tampered'},format='json').status_code,400)
    def test_test_push_traverses_outbox_and_status_hides_capabilities(self):
        self.client.force_authenticate(self.worker)
        PushSubscription.objects.create(organization=self.company,user=self.worker,endpoint='https://fcm.googleapis.com/fcm/send/other-phone',p256dh='key',auth='key')
        result=self.client.post('/api/push/test/',{'endpoint':self.sub.endpoint},format='json');self.assertEqual(result.status_code,202,result.data)
        row=PlanningPushDelivery.objects.get(notification_id=result.data['id']);self.assertEqual(row.state,'PENDING')
        response=self.client.get('/api/push/status/');serialized=json.dumps(response.data);self.assertNotIn('private-endpoint',serialized);self.assertNotIn('test-auth',serialized)
        self.client.force_authenticate(self.admin);self.assertEqual(self.client.get('/api/push/test/'+str(row.notification_id)+'/').status_code,404)
    def test_provider_acceptance_is_not_confirmation_and_sends_are_bounded(self):
        self.ticket();row=PushDelivery.objects.get();row.state='SENT';row.attempts=1;row.next_attempt_at=timezone.now()-timedelta(seconds=1);row.save()
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one',return_value='SENT') as send:
            self.assertEqual(process_batch(),1);send.assert_called_once()
        row.refresh_from_db();self.assertEqual(row.attempts,2);self.assertEqual(row.state,'SENT')
        row.state='DISPLAYED';row.next_attempt_at=timezone.now()-timedelta(seconds=1);row.save()
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one') as send:
            self.assertEqual(process_batch(),0);send.assert_not_called()
    def test_show_receipt_race_cannot_be_overwritten_by_provider_acceptance(self):
        self.ticket();row=PushDelivery.objects.get()
        def send(item,config):PushDelivery.objects.filter(pk=item.pk).update(state='DISPLAYED');return 'SENT'
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one',side_effect=send):process_batch()
        row.refresh_from_db();self.assertEqual(row.state,'DISPLAYED')

    def test_real_browser_session_can_register_and_create_push_event(self):
        self.client.force_authenticate(None)
        self.assertTrue(self.client.login(username='admin',password='long-test-password'))
        with patch('core.push_notifications.push_config',return_value=self.config):
            response=self.client.post('/api/push/subscription/',{'expected_user':self.admin.pk,'endpoint':'https://fcm.googleapis.com/fcm/send/session-device','keys':{'p256dh':'abcdefghijklmnop','auth':'abcdefghijklmnop'}},format='json')
        self.assertEqual(response.status_code,201,response.data)
        import uuid
        response=self.client.post('/api/mobile/sync/',{'id':str(uuid.uuid4()),'type':'create','occurred_at':timezone.now().isoformat(),'body':{'elevator':self.lift.pk,'title':'Browser session event'}},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertTrue(PushDelivery.objects.filter(ticket_id=response.data['ticket']['id']).exists())
