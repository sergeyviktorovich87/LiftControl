from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from . import tests_push_reliability as fixture
from .models import TicketDeliveryReceipt,DutyShift,Ticket,NotificationInbox,PushDelivery,TicketEvent,ChatMessage


class TicketNotificationRulesTests(TestCase):
    setUp=fixture.PushReliabilityTests.setUp
    user=fixture.PushReliabilityTests.user
    ticket=fixture.PushReliabilityTests.ticket

    def test_creator_does_not_receive_own_ticket_but_other_user_does(self):
        DutyShift.objects.create(organization=self.company,technician=self.tech,start=timezone.now()-timedelta(hours=1),end=timezone.now()+timedelta(hours=1))
        self.client.force_authenticate(self.worker)
        result=self.client.post('/api/tickets/',{'elevator':self.lift.pk,'title':'Своя заявка','priority':'ENTRAPMENT'},format='json')
        self.assertEqual(result.status_code,201,result.data)
        ticket=Ticket.objects.get(pk=result.data['id'])
        self.assertFalse(NotificationInbox.objects.filter(user=self.worker,target_type='ticket',target_id=ticket.pk).exists())
        self.assertFalse(PushDelivery.objects.filter(ticket=ticket,subscription=self.sub).exists())
        self.assertTrue(NotificationInbox.objects.filter(user=self.admin,target_type='ticket',target_id=ticket.pk).exists())
        self.assertEqual(self.client.get('/api/notifications/counts/').data['unread'],0)
        self.assertFalse(TicketDeliveryReceipt.objects.filter(ticket=ticket).exists())

    def test_chat_stays_in_history_without_becoming_own_incoming(self):
        message=ChatMessage.objects.create(organization=self.company,author=self.worker,body='Моё сообщение')
        from .notification_inbox import enqueue_team_chat,_visible_inbox
        enqueue_team_chat(message)
        self.assertFalse(NotificationInbox.objects.filter(user=self.worker,target_type='chat').exists())
        self.assertTrue(NotificationInbox.objects.filter(user=self.admin,target_type='chat').exists())
        own=NotificationInbox.objects.create(organization=self.company,user=self.worker,event_type='team_chat',event_id=message.pk,kind='message',target_type='chat',target_id=message.pk,title='Старая собственная запись')
        self.assertFalse(_visible_inbox(self.worker,self.company).filter(pk=own.pk).exists())

    def test_cancel_keeps_history_without_new_notifications_or_queued_push(self):
        ticket=self.ticket();before=NotificationInbox.objects.count()
        response=self.client.post(f'/api/tickets/{ticket.pk}/cancel/',{'reason':'Ошибочная заявка, дубликат'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(NotificationInbox.objects.count(),before)
        self.assertFalse(PushDelivery.objects.filter(ticket=ticket,kind='canceled').exists())
        self.assertTrue(ticket.events.filter(action='canceled',reason='Ошибочная заявка, дубликат').exists())
        from .push_notifications import deliver_one
        self.assertEqual(deliver_one(PushDelivery.objects.get(ticket=ticket),self.config),'SUPERSEDED')

    def test_release_to_repair_requires_confirmation_and_keeps_workflow(self):
        ticket=self.ticket();ticket.priority='ENTRAPMENT';ticket.status='IN_PROGRESS';ticket.assigned_to=self.tech;ticket.accepted_at=timezone.now();ticket.save()
        self.client.force_authenticate(self.worker)
        path=f'/api/tickets/{ticket.pk}/change-type/'
        body={'priority':'NORMAL','reason':'Люди освобождены, ремонт дверей'}
        self.assertEqual(self.client.post(path,body,format='json').status_code,400)
        body['people_released']=True
        response=self.client.post(path,body,format='json');self.assertEqual(response.status_code,200,response.data)
        ticket.refresh_from_db();self.assertEqual((ticket.priority,ticket.status,ticket.assigned_to_id),('NORMAL','IN_PROGRESS',self.tech.pk))
        event=ticket.events.get(action='type_changed');self.assertEqual((event.before,event.after,event.actor_id),('ENTRAPMENT','NORMAL',self.worker.pk))
        ticket.status='DONE';ticket.save()
        self.assertEqual(self.client.post(path,{'priority':'HIGH','reason':'Изменение после закрытия'},format='json').status_code,403)

    def test_unassigned_mechanic_cannot_change_type(self):
        ticket=self.ticket();other=self.user('other-worker','MECHANIC',None);self.client.force_authenticate(other)
        response=self.client.post(f'/api/tickets/{ticket.pk}/change-type/',{'priority':'HIGH','reason':'Изменение чужой заявки'},format='json')
        self.assertIn(response.status_code,(403,404))
