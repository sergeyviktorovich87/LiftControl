from datetime import datetime, timedelta, timezone as utc
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .inspection_reminders import enqueue_due_inspections
from .uploads import MAX_FILE_BYTES
from .models import Building, Elevator, LiftDocument, Membership, NotificationInbox, Organization, Technician


class LiftDocumentTests(TestCase):
    def setUp(self):
        company = self.company = Organization.objects.create(name='Лифт Тест', timezone='Asia/Chita')
        foreign = self.foreign = Organization.objects.create(name='Другая организация')
        users = get_user_model().objects
        self.admin = users.create_user('test-lift-admin')
        self.mechanic = users.create_user('test-lift-mech')
        self.other = users.create_user('test-lift-other')
        self.director = users.create_user('test-lift-director')
        self.technician = Technician.objects.create(organization=company, full_name='Один')
        self.other_technician = Technician.objects.create(organization=company, full_name='Два')
        for user, role, tech in [
            (self.admin, 'ADMIN', None), (self.mechanic, 'MECHANIC', self.technician),
            (self.other, 'MECHANIC', self.other_technician), (self.director, 'DIRECTOR', None),
        ]:
            Membership.objects.create(organization=company, user=user, role=role, technician=tech)
        Membership.objects.create(organization=foreign, user=self.admin, role='ADMIN')
        building = Building.objects.create(organization=company, address='50 лет Октября 265')
        self.lift = Elevator.objects.create(organization=company, building=building,
            assigned_technician=self.technician, entrance='1 (левый)')
        self.client = APIClient()

    def sign_in(self, user, organization=None):
        self.client.force_authenticate(user)
        self.client.credentials(HTTP_X_ORGANIZATION_ID=str((organization or self.company).pk))

    def upload(self, category, content=b'%PDF-1.7\n% test'):
        return self.client.post('/api/lift-documents/', {
            'elevator': self.lift.pk, 'category': category, 'title': 'Документ '+category,
            'file': SimpleUploadedFile('fixture.pdf', content, content_type='application/pdf'),
        }, format='multipart')

    def test_pdf_upload_at_100_mib_and_one_byte_over(self):
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder, FILE_UPLOAD_TEMP_DIR=folder):
            self.sign_in(self.admin)
            content = b'%PDF-1.7\n'.ljust(MAX_FILE_BYTES, b' ')
            reply = self.upload('CONTRACT', content)
            self.assertEqual(reply.status_code, 201, reply.data)
            document = LiftDocument.objects.get(pk=reply.data['id'])
            self.assertEqual(document.file.size, 104_857_600)
            reply = self.upload('CONTRACT', content + b' ')
            self.assertEqual(reply.status_code, 400, reply.data)
            self.assertIn('100 МБ', str(reply.data))
            self.assertEqual(LiftDocument.objects.count(), 1)

    def test_private_document_types_and_read_only_acts(self):
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.sign_in(self.admin)
            self.assertEqual(self.upload('CONTRACT', b'<html>').status_code, 400)
            contract = self.upload('CONTRACT')
            act = self.upload('INSPECTION')
            order = self.upload('ORDER')
            for reply in (contract, act, order):
                self.assertEqual(reply.status_code, 201, reply.data)
            self.sign_in(self.admin, self.foreign)
            self.assertEqual(self.client.get(act.data['url']).status_code, 404)
            self.assertEqual(self.upload('INSPECTION').status_code, 404)
            for person in (self.mechanic, self.other, self.director):
                self.sign_in(person)
                self.assertEqual(self.upload('INSPECTION').status_code, 403)
                self.assertEqual(self.client.get('/api/lift-documents/').status_code, 403)
                self.assertEqual(self.client.get(contract.data['url']).status_code, 404)
                self.assertEqual(self.client.get(order.data['url']).status_code, 404)
                self.assertEqual(self.client.delete('/api/lift-documents/%s/' % act.data['id']).status_code, 403)
                card = self.client.get(f'/api/lift-inspections/{self.lift.pk}/').data
                self.assertEqual([doc['id'] for doc in card['acts']], [act.data['id']])
                view = self.client.get(act.data['url'])
                self.assertEqual(view.status_code, 200)
                self.assertIn('no-store', view.headers['Cache-Control'])
                self.assertTrue(b''.join(view.streaming_content).startswith(b'%PDF-'))
            self.sign_in(self.admin)
            self.assertEqual(self.client.delete('/api/lift-documents/%s/' % act.data['id']).status_code, 204)
            self.sign_in(self.mechanic)
            self.assertEqual(self.client.get(act.data['url']).status_code, 404)

    def test_five_local_mornings_and_rescheduling(self):
        first = datetime(2026, 11, 22, 0, 0, tzinfo=utc.utc)
        due = (first+timedelta(days=5)).date()
        with patch('core.lift_documents.timezone.localdate', return_value=first.date()):
            route = f'/api/lift-inspections/{self.lift.pk}/'
            self.sign_in(self.mechanic)
            self.assertEqual(self.client.patch(route, {'date': due.isoformat()}, format='json').status_code, 403)
            self.sign_in(self.admin)
            self.assertEqual(self.client.patch(route, {'date': due.isoformat()}, format='json').status_code, 200)
        self.assertEqual(enqueue_due_inspections(first-timedelta(minutes=1)), 0)
        for day in range(5):
            morning = first + timedelta(days=day)
            self.assertEqual(enqueue_due_inspections(morning), 1)
            self.assertEqual(enqueue_due_inspections(morning+timedelta(minutes=1)), 0)
        self.assertEqual(enqueue_due_inspections(first+timedelta(days=5)), 0)
        self.sign_in(self.mechanic)
        rows = self.client.get('/api/notifications/?category=ordinary').data['results']
        self.assertEqual(len(rows), 5)
        self.assertIn('50 лет Октября 265', rows[0]['title'])
        self.assertIn('27.11.2026', rows[0]['title'])
        self.assertEqual(self.client.get('/api/notifications/counts/').data['sections']['elevators'], 5)
        self.sign_in(self.other)
        self.assertEqual(self.client.get('/api/notifications/').data['unread'], 0)
        self.sign_in(self.admin)
        self.assertEqual(self.client.patch(route, {'date': None}, format='json').status_code, 200)
        self.sign_in(self.mechanic)
        self.assertEqual(self.client.get('/api/notifications/').data['unread'], 0)

    def test_filters_do_not_mix_entrapments_and_ordinary_inbox(self):
        for event_id, critical in [(101, False), (102, True)]:
            NotificationInbox.objects.create(organization=self.company, user=self.mechanic,
                event_type='ticket', event_id=event_id, target_type='ticket', target_id=event_id,
                title='Заявка', kind='created', is_entrapment=critical)
        self.sign_in(self.mechanic)
        critical = self.client.get('/api/notifications/?category=entrapment').data
        self.assertEqual(critical['unread_by_category'], {'ordinary': 1, 'entrapment': 1})
        self.assertEqual([item['target_id'] for item in critical['results']], [102])
        ordinary = self.client.get('/api/notifications/?category=ordinary').data
        self.assertEqual([item['target_id'] for item in ordinary['results']], [101])
        self.assertEqual(self.client.get('/api/notifications/counts/').data['entrapment'], 1)
