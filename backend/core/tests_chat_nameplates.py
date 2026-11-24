"""0.13.14: chat links, private nameplates, replay and lift identifiers."""
import io
import tempfile
import uuid
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from .models import (Organization, Membership, Building, Elevator, ChatMessage, MediaAsset,
                     CommissioningProject, CommissioningLift, CommissioningAssignment,
                     CommissioningNameplate)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ChatNameplateTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.org = Organization.objects.get(pk=1)
        self.other = Organization.objects.create(name='Другая')
        self.admin = get_user_model().objects.create_user('admin-14')
        self.worker = get_user_model().objects.create_user('worker-14')
        self.peer = get_user_model().objects.create_user('peer-14')
        Membership.objects.create(user=self.admin, organization=self.org, role='ADMIN')
        Membership.objects.create(user=self.admin, organization=self.other, role='ADMIN')
        for user in (self.worker, self.peer):
            Membership.objects.create(user=user, organization=self.org, role='ADJUSTER', can_commissioning=True)
        self.project = CommissioningProject.objects.create(organization=self.org, name='Объект', address='Адрес')
        self.lift = CommissioningLift.objects.create(project=self.project, label='Лифт 20')
        self.second = CommissioningLift.objects.create(project=self.project, label='Лифт 21')
        CommissioningAssignment.objects.create(lift=self.lift, user=self.worker)
        CommissioningAssignment.objects.create(lift=self.second, user=self.peer)
        self.route = f'/api/commissioning/{self.project.pk}/lifts/{self.lift.pk}/nameplates/'
        self.client = APIClient()
        self.client.force_authenticate(self.worker)
        self.message = ChatMessage.objects.create(organization=self.org, author=self.worker, body='Проверить лифт')
        output = io.BytesIO()
        Image.new('RGB', (640, 480), 'blue').save(output, 'PNG')
        self.image = output.getvalue()

    def photo(self):
        return SimpleUploadedFile('plate.png', self.image, content_type='image/png')

    def send_plate(self, **extra):
        return self.client.post(self.route, {'photos': [self.photo()], 'description': 'Ограничитель скорости', **extra}, format='multipart')

    def test_nameplate_private_photo_and_assignment_revocation(self):
        response = self.send_plate()
        self.assertEqual(response.status_code, 201, response.content)
        data = self.client.get(self.route).json()[0]
        self.assertEqual(data['description'], 'Ограничитель скорости')
        photo = self.client.get(data['url'])
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(b''.join(photo.streaming_content), self.image)
        preview = self.client.get(data['preview_url'])
        self.assertEqual(preview.status_code, 200)
        # Consume the stream; response.close() emits request_finished and
        # closes PostgreSQL's outer TestCase transaction.
        self.assertTrue(b''.join(preview.streaming_content))
        self.client.force_authenticate(self.peer)
        self.assertEqual(self.client.get(self.route).status_code, 403)
        self.assertEqual(self.client.get(data['url']).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.route).status_code, 200)
        self.assertEqual(self.send_plate().status_code, 403)
        self.assertEqual(self.client.get(self.route, HTTP_X_ORGANIZATION_ID=str(self.other.pk)).status_code, 404)
        CommissioningAssignment.objects.filter(lift=self.lift, user=self.worker).update(active=False)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(data['preview_url']).status_code, 403)

    def test_nameplate_retry_is_idempotent_and_changes_conflict(self):
        operation = str(uuid.uuid4())
        first = self.send_plate(operation_id=operation)
        again = self.send_plate(operation_id=operation)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.json(), again.json())
        self.assertEqual(CommissioningNameplate.objects.count(), 1)
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(self.send_plate(operation_id=operation, description='Другое').status_code, 409)

    def test_missing_caption_photo_and_invalid_photo_leave_no_records(self):
        self.assertEqual(self.send_plate(description='').status_code, 400)
        self.assertEqual(self.client.post(self.route, {'description': 'Шильдик'}, format='json').status_code, 400)
        bad = SimpleUploadedFile('bad.png', b'not an image', content_type='image/png')
        result = self.client.post(self.route, {'description': 'Шильдик', 'photos': [self.photo(), bad]}, format='multipart')
        self.assertEqual(result.status_code, 400, result.content)
        self.assertEqual(CommissioningNameplate.objects.count(), 0)
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_archived_project_is_read_only(self):
        self.assertEqual(self.send_plate().status_code, 201)
        self.project.archived_at = timezone.now()
        self.project.save()
        self.assertEqual(self.client.get(self.route).status_code, 200)
        self.assertEqual(self.send_plate().status_code, 400)
        self.assertEqual(CommissioningNameplate.objects.count(), 1)

    def test_chat_reply_stays_in_organization(self):
        self.client.force_authenticate(self.admin)
        reply = self.client.post('/api/chat/', {'body': 'Принял', 'reply_to': self.message.pk}, format='json')
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertEqual(reply.json()['reply']['body'], 'Проверить лифт')
        other = ChatMessage.objects.create(organization=self.other, author=self.admin, body='Секрет')
        result = self.client.post('/api/chat/', {'body': 'Ответ', 'reply_to': other.pk}, format='json')
        self.assertEqual(result.status_code, 400)
        rows = self.client.get('/api/chat/').json()
        self.assertFalse(any(row['id'] == other.pk for row in rows))

    def test_pin_requires_admin_one_pin_and_survives_recent_message_limit(self):
        path = f'/api/chat/{self.message.pk}/pin/'
        self.assertEqual(self.client.post(path, {'pinned': True}, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(path, {'pinned': 'false'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(path, {'pinned': True}, format='json').status_code, 200)
        ChatMessage.objects.bulk_create([ChatMessage(organization=self.org, author=self.admin, body=str(n)) for n in range(205)])
        self.assertEqual(self.client.get('/api/chat/pinned/').json()['message']['id'], self.message.pk)
        newest = ChatMessage.objects.order_by('-id').first()
        self.assertEqual(self.client.post(f'/api/chat/{newest.pk}/pin/', {'pinned': True}, format='json').status_code, 200)
        self.assertEqual(ChatMessage.objects.filter(pinned=True).count(), 1)
        self.assertEqual(self.client.get('/api/chat/pinned/', HTTP_X_ORGANIZATION_ID=str(self.other.pk)).json()['message'], None)
        self.assertEqual(self.client.post(f'/api/chat/{newest.pk}/pin/', {'pinned': False}, format='json').status_code, 200)
        self.assertIsNone(self.client.get('/api/chat/pinned/').json()['message'])

    def test_offline_media_reply_validated_and_replayed(self):
        self.client.force_authenticate(self.admin)
        data = {'upload_id': str(uuid.uuid4()), 'kind': 'chat', 'message_key': str(uuid.uuid4()), 'body': 'Ответ из очереди', 'reply_to': str(self.message.pk)}
        first = self.client.post('/api/media/uploads/', data, format='multipart')
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client.post('/api/media/uploads/', data, format='multipart')
        self.assertEqual(second.status_code, 200, second.content)
        self.assertTrue(second.json()['replayed'])
        self.assertEqual(ChatMessage.objects.get(body='Ответ из очереди').reply_to_id, self.message.pk)
        other = ChatMessage.objects.create(organization=self.other, author=self.admin, body='Другое')
        data.update(upload_id=str(uuid.uuid4()), message_key=str(uuid.uuid4()), reply_to=str(other.pk))
        self.assertEqual(self.client.post('/api/media/uploads/', data, format='multipart').status_code, 404)

    def test_entrance_default_and_lift_number_round_trip(self):
        self.client.force_authenticate(self.admin)
        building = Building.objects.create(organization=self.org, name='ТЦ', address='Центр')
        lift = Elevator.objects.create(organization=self.org, building=building, entrance='20')
        self.assertEqual(lift.entrance_kind, 'ENTRANCE')
        route = f'/api/elevators/{lift.pk}/'
        result = self.client.patch(route, {'entrance_kind': 'LIFT'}, format='json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual((result.json()['entrance'], result.json()['entrance_kind']), ('20', 'LIFT'))
        self.assertEqual(self.client.patch(route, {'entrance_kind': 'UNKNOWN'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(route, {'notes': 'Старый клиент'}, format='json').status_code, 200)
        lift.refresh_from_db()
        self.assertEqual((lift.entrance, lift.entrance_kind), ('20', 'LIFT'))
