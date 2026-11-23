from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (Organization, Membership, ChatMessage, NotificationInbox,
                     MobileSession, Technician, Building, Elevator, Ticket)
from .notification_inbox import enqueue_team_chat
from .notification_content import content_token


class MessageReceiptTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.get(pk=1)
        self.other = Organization.objects.create(name='Другие')
        self.sender = get_user_model().objects.create_user('sender', password='test-secure-password')
        self.recipient = get_user_model().objects.create_user('recipient', password='test-secure-password')
        self.member = Membership.objects.create(user=self.recipient, organization=self.org, role='ADMIN')
        Membership.objects.create(user=self.sender, organization=self.org, role='ADMIN')
        self.message = ChatMessage.objects.create(organization=self.org, author=self.sender, body='Текст\n' * 800)
        enqueue_team_chat(self.message)
        self.row = NotificationInbox.objects.get(user=self.recipient, event_type='team_chat')
        self.client = APIClient()
        self.client.force_authenticate(self.recipient)

    def ack(self, **changes):
        return self.client.post('/api/notifications/receipts/',
            {'target': 'chat', 'ids': [self.message.pk], **changes}, format='json',
            HTTP_X_ORGANIZATION_ID=str(self.org.pk))

    def test_delivery_and_read_are_distinct_and_idempotent(self):
        self.assertEqual(self.ack().status_code, 200)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.delivered_at)
        self.assertIsNone(self.row.message_read_at)
        self.assertIsNone(self.row.read_at)
        delivered = self.row.delivered_at
        self.assertEqual(self.ack(read=True).status_code, 200)
        self.row.refresh_from_db()
        read = self.row.message_read_at
        self.ack(read=True)
        self.row.refresh_from_db()
        self.assertEqual((self.row.delivered_at, self.row.message_read_at), (delivered, read))
        self.client.force_authenticate(self.sender)
        data = self.client.get('/api/chat/').data
        self.assertEqual(data[0]['receipt'], {'total': 1, 'delivered': 1, 'read': 1})

    def test_opening_notification_does_not_mark_message_read(self):
        self.client.post(f'/api/notifications/{self.row.pk}/read/', {}, format='json')
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.read_at)
        self.assertIsNone(self.row.message_read_at)

    def test_ack_cannot_touch_other_recipient_or_organization(self):
        foreign = NotificationInbox.objects.create(organization=self.other, user=self.recipient,
            event_type='team_chat', event_id=999, kind='message', title='Other', target_type='chat', target_id=999)
        self.ack(ids=[999], read=True)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.delivered_at)
        self.client.force_authenticate(self.sender)
        self.ack(read=True)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.delivered_at)

    def test_full_text_and_signed_content_recheck_membership(self):
        data = self.client.get('/api/notifications/').data
        self.assertEqual(data['results'][0]['body'], self.message.body)
        session = MobileSession.objects.create(user=self.recipient, token_hash='a' * 64,
            password_stamp=self.recipient.get_session_auth_hash(), expires_at=timezone.now()+timedelta(days=1))
        token = content_token(session, self.org.pk, 'inbox', self.row.pk)
        self.client.force_authenticate(None)
        response = self.client.post('/api/mobile/push/content/', {'token': token}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['body'], self.message.body)
        self.assertGreater(len(response.data['body'].encode()), 4000)
        self.member.active = False
        self.member.save()
        self.assertEqual(self.client.post('/api/mobile/push/content/', {'token': token}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/mobile/push/content/', {'token': token+'x'}, format='json').status_code, 403)

    def test_reading_dispatch_does_not_accept_work(self):
        from .ticket_flow import create_ticket
        tech = Technician.objects.create(organization=self.org, full_name='Механик')
        self.member.role, self.member.technician = 'MECHANIC', tech
        self.member.save()
        building = Building.objects.create(organization=self.org, name='Дом', address='Адрес')
        lift = Elevator.objects.create(organization=self.org, building=building, assigned_technician=tech)
        self.sender._organization_id = self.org.pk
        ticket = create_ticket(self.sender, {'elevator': lift, 'title': 'Заявка', 'description': 'Текст'})
        self.assertEqual(self.ack(target='ticket', ids=[ticket.pk], read=True).status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.NEW)
        receipt = ticket.delivery_receipts.get(recipient=self.recipient)
        self.assertIsNotNone(receipt.read_at)
        self.assertIsNotNone(receipt.received_at)
