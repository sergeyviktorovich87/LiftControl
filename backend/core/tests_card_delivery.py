from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (Building, Document, DutyShift, DutySwap, Elevator, Membership,
                     MobileSession, NotificationInbox, Organization, Technician, TicketDeliveryReceipt)
from .ticket_delivery import enqueue_due_receipt_warnings, push_token


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CardDeliveryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.get(pk=1)
        self.other_org = Organization.objects.create(name='Другая организация')
        user = get_user_model()
        self.admin = user.objects.create_user('card-admin')
        self.mechanic = user.objects.create_user('card-mechanic', password='strong-test-password')
        self.other = user.objects.create_user('another-mechanic')
        self.tech = Technician.objects.create(organization=self.org, full_name='Механик А')
        self.other_tech = Technician.objects.create(organization=self.org, full_name='Механик Б')
        Membership.objects.create(user=self.admin, organization=self.org, role='ADMIN')
        Membership.objects.create(user=self.mechanic, organization=self.org, role='MECHANIC', technician=self.tech)
        Membership.objects.create(user=self.other, organization=self.org, role='MECHANIC', technician=self.other_tech)
        self.building = Building.objects.create(organization=self.org, name='Дом', address='Проверочный 1')
        self.lift = Elevator.objects.create(organization=self.org, building=self.building,
                                            manufacturer='МЭЛ', model='AS380', assigned_technician=self.tech)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.credentials(HTTP_X_ORGANIZATION_ID=str(self.org.pk))

    def create_ticket(self):
        response = self.client.post('/api/tickets/', {'elevator': self.lift.pk, 'title': 'Проверка'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['delivery']['state'], 'pending')
        return response.data['id']

    def test_receipt_requires_matching_mobile_user_or_valid_push_capability(self):
        ticket_id = self.create_ticket()
        row = TicketDeliveryReceipt.objects.get(ticket_id=ticket_id)
        self.assertEqual(row.recipient_id, self.mechanic.pk)
        self.assertIsNone(row.received_at)
        body = {'ids': [row.pk]}
        self.assertEqual(self.client.post('/api/mobile/ticket-delivery/', body, format='json').status_code, 403)

        phone = APIClient()
        logged_in = phone.post('/api/mobile/login/', {'username': self.mechanic.username,
                               'password': 'strong-test-password', 'device_name': 'QA'}, format='json')
        self.assertEqual(logged_in.status_code, 200, logged_in.data)
        session = MobileSession.objects.get(user=self.mechanic)
        capability = push_token(row.event_id, session)
        self.assertEqual(phone.post('/api/mobile/ticket-delivery/push/', {'receipt': capability + 'x'},
                                    format='json').status_code, 403)
        self.assertEqual(phone.post('/api/mobile/ticket-delivery/push/', {'receipt': capability},
                                    format='json').status_code, 204)
        phone.credentials(HTTP_AUTHORIZATION='Bearer ' + logged_in.data['token'])
        self.assertEqual(phone.post('/api/mobile/ticket-delivery/', body, format='json').data['updated'], 0)
        status = self.client.get(f'/api/tickets/{ticket_id}/').data
        self.assertEqual(status['status'], 'NEW')
        self.assertEqual(status['delivery']['state'], 'received')
        self.assertIsNotNone(status['delivery']['received_at'])

    def test_timeout_is_sent_once_only_to_sender_and_late_receipt_changes_status(self):
        ticket_id = self.create_ticket()
        row = TicketDeliveryReceipt.objects.get(ticket_id=ticket_id)
        self.assertEqual(enqueue_due_receipt_warnings(), 0)
        TicketDeliveryReceipt.objects.filter(pk=row.pk).update(warn_after=timezone.now()-timedelta(seconds=1))
        self.assertEqual(enqueue_due_receipt_warnings(), 1)
        self.assertEqual(enqueue_due_receipt_warnings(), 0)
        alert = NotificationInbox.objects.get(event_type='ticket_delivery')
        self.assertEqual((alert.user_id, alert.target_id), (self.admin.pk, ticket_id))
        self.assertIsNotNone(alert.commissioning_push_after)
        self.assertEqual(self.client.get(f'/api/tickets/{ticket_id}/').data['delivery']['state'], 'unconfirmed')
        session = MobileSession.objects.create(user=self.mechanic, token_hash='qa-device',
                                              password_stamp=self.mechanic.get_session_auth_hash(),
                                              expires_at=timezone.now()+timedelta(hours=1))
        self.client.force_authenticate(self.mechanic, token=session)
        self.assertEqual(self.client.post('/api/mobile/ticket-delivery/', {'ids': [row.pk]},
                                         format='json').data['updated'], 1)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'/api/tickets/{ticket_id}/').data['delivery']['state'], 'received')

    def test_lift_document_matching_explicit_missing_numbers_and_safe_address_changes(self):
        edit = self.client.patch(f'/api/elevators/{self.lift.pk}/',
                                 {'documentation_tags': ' AS380 ,  привод  дверей ', 'inventory_number_missing': True},
                                 format='json')
        self.assertEqual(edit.status_code, 200, edit.data)
        self.assertTrue(edit.data['inventory_number_missing'])
        self.assertEqual(edit.data['inventory_number'], '')
        another = self.client.post('/api/elevators/', {'building':self.building.pk,
                                  'inventory_number': 'Нет'}, format='json')
        self.assertEqual(another.status_code, 201, another.data)
        self.assertTrue(another.data['inventory_number_missing'])
        for organization, title, manufacturer, model, tags in [
            (self.org, 'Legacy', 'мэл', 'as380', ''),
            (self.org, 'Both tags', '', '', 'as380, привод дверей'),
            (self.org, 'Missing tag', 'МЭЛ', 'AS380', 'as380, as320'),
            (self.other_org, 'Foreign', 'МЭЛ', '', 'as380'),
        ]:
            Document.objects.create(organization=organization, title=title, manufacturer=manufacturer,
                                    model=model, documentation_tags=tags, file='ignored.pdf')
        docs = self.client.get(f'/api/elevators/{self.lift.pk}/documents/').data
        self.assertEqual({doc['title'] for doc in docs}, {'Legacy', 'Both tags'})
        self.assertEqual(self.client.delete(f'/api/buildings/{self.building.pk}/').status_code, 400)
        changed = self.client.patch(f'/api/buildings/{self.building.pk}/',
                                    {'address': 'Обновлённый 2'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get(f'/api/elevators/{self.lift.pk}/').data['address'], 'Обновлённый 2')
        empty = Building.objects.create(organization=self.org, name='Пустой', address='Пустой 1')
        self.assertEqual(self.client.delete(f'/api/buildings/{empty.pk}/').status_code, 204)

    def test_duty_analytics_counts_actual_shift_and_only_accepted_swaps(self):
        now = timezone.now()
        shift = DutyShift.objects.create(organization=self.org, technician=self.other_tech,
                                        start=now-timedelta(days=2), end=now-timedelta(days=1))
        for status in ('ACCEPTED','CANCELED'):
            DutySwap.objects.create(organization=self.org, shift=shift, source_technician=self.tech,
                                    target_technician=self.other_tech, shift_version=shift.updated_at,
                                    requested_by=self.mechanic, status=status)
        local_day = shift.start.astimezone(ZoneInfo(self.org.timezone)).date()
        url = f'/api/analytics/duty/?from={local_day}&to={local_day}'
        report = self.client.get(url)
        self.assertEqual(report.status_code, 200)
        rows = {item['id']: item for item in report.data['technicians']}
        self.assertEqual((rows[self.tech.pk]['completed'], rows[self.tech.pk]['swaps_out']), (0, 1))
        self.assertEqual((rows[self.other_tech.pk]['completed'], rows[self.other_tech.pk]['swaps_in']), (1, 1))
        self.assertEqual(len(report.data['swaps']), 1)
        self.client.force_authenticate(self.mechanic)
        self.assertEqual(self.client.get(url).status_code, 403)
