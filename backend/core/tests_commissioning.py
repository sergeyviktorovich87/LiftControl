"""Commissioning security, tenant isolation, progress race and expense regressions."""
import io
import tempfile
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .media_vault import atomic_media, ingest
from .models import (Organization, Membership, Technician, Building, Elevator,
                     CommissioningProject, CommissioningLift, CommissioningAssignment,
                     CommissioningProgress, CommissioningExpense, CommissioningExtraWork,
                     CommissioningPhoto, CommissioningMessage, NotificationInbox)


class CommissioningTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.org = Organization.objects.get(pk=1)
        self.foreign = Organization.objects.create(name='Прочая организация')
        User = get_user_model()
        self.admin = User.objects.create_user(username='director-13', password='VeryStrong13Password!')
        self.a = User.objects.create_user(username='adjuster-a', password='VeryStrong13Password!')
        self.b = User.objects.create_user(username='adjuster-b', password='VeryStrong13Password!')
        self.stranger = User.objects.create_user(username='third-company', password='VeryStrong13Password!')
        Membership.objects.create(organization=self.org, user=self.admin, role='ADMIN')
        Membership.objects.create(organization=self.org, user=self.a, role='ADJUSTER', can_commissioning=True)
        Membership.objects.create(organization=self.org, user=self.b, role='ADJUSTER', can_commissioning=True)
        Membership.objects.create(organization=self.foreign, user=self.stranger, role='ADMIN')
        self.project = CommissioningProject.objects.create(
            organization=self.org, name='ЖК', address='Первый 1', created_by=self.admin)
        self.lift_a = CommissioningLift.objects.create(project=self.project, label='Лифт А')
        self.lift_b = CommissioningLift.objects.create(project=self.project, label='Лифт Б')
        CommissioningAssignment.objects.create(lift=self.lift_a, user=self.a)
        CommissioningAssignment.objects.create(lift=self.lift_b, user=self.b)
        self.client = APIClient()

    def request(self, user, method, path, body=None, tenant=None, format='json'):
        self.client.force_authenticate(user)
        headers = {'HTTP_X_ORGANIZATION_ID': str((tenant or self.org).id)}
        endpoint = '/api/' + path
        if method == 'get':
            return self.client.get(endpoint, **headers)
        return self.client.post(endpoint, body or {}, format=format, **headers)

    def test_project_shared_overview_but_strict_progress_authority(self):
        self.assertEqual(self.request(self.a, 'get', 'commissioning/').status_code, 200)
        response = self.request(self.a, 'get', f'commissioning/{self.project.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['lifts']), 2)
        self.assertTrue(response.data['lifts'][0]['can_edit'])
        self.assertFalse(response.data['lifts'][1]['can_edit'])
        path = f'commissioning/{self.project.pk}/lifts/{self.lift_b.pk}/progress/'
        self.assertEqual(self.request(self.a, 'post', path,
            {'revision': 0, 'progress': 20, 'description': 'Проверка дверей'}).status_code, 403)
        self.assertEqual(self.request(self.admin, 'post', path,
            {'revision': 0, 'progress': 20, 'description': 'Администратор'}).status_code, 403)
        self.assertEqual(self.request(self.b, 'post', path,
            {'revision': 0, 'progress': 20, 'description': 'Датчики выставлены'}).status_code, 200)
        self.assertEqual(self.request(self.b, 'post', path,
            {'revision': 0, 'progress': 80, 'description': 'Повтор'}).status_code, 400)
        self.lift_b.refresh_from_db()
        self.assertEqual((self.lift_b.progress, self.lift_b.revision), (20, 1))
        self.assertEqual(CommissioningProgress.objects.filter(lift=self.lift_b).count(), 1)

    def test_personal_expenses_and_receipts_private_even_on_common_project(self):
        path = f'commissioning/{self.project.pk}/expenses/'
        self.assertEqual(self.request(self.a, 'post', path,
            {'amount': '140.10', 'description': 'Болты'}).status_code, 201)
        self.assertEqual(self.request(self.b, 'post', path,
            {'amount': '70', 'description': 'Проезд'}).status_code, 201)
        expenses = CommissioningExpense.objects.filter(project=self.project).order_by('id')
        own, other = list(expenses)
        a = self.request(self.a, 'get', f'commissioning/{self.project.pk}/').data
        self.assertEqual([x['id'] for x in a['expenses']], [own.pk])
        b = self.request(self.b, 'get', f'commissioning/{self.project.pk}/').data
        self.assertEqual([x['id'] for x in b['expenses']], [other.pk])
        director = self.request(self.admin, 'get', f'commissioning/{self.project.pk}/').data
        self.assertEqual(len(director['expenses']), 2)
        im = Image.new('RGB', (4, 4), color='white')
        stream = io.BytesIO()
        im.save(stream, format='PNG')
        upload = SimpleUploadedFile('check.png', stream.getvalue(), content_type='image/png')
        uri = f'commissioning/{self.project.pk}/expenses/{own.pk}/upload/'
        self.assertEqual(self.request(self.a, 'post', uri, {'receipt': upload}, format='multipart').status_code, 201)
        duplicate = SimpleUploadedFile('another.png', stream.getvalue(), content_type='image/png')
        self.assertEqual(self.request(self.a, 'post', uri, {'receipt': duplicate}, format='multipart').status_code, 400)
        uri = f'commissioning/{self.project.pk}/expenses/{own.pk}/receipt/'
        self.assertEqual(self.request(self.b, 'get', uri).status_code, 403)
        self.assertEqual(self.request(self.a, 'get', uri).status_code, 200)
        self.assertEqual(self.request(self.admin, 'get', uri).status_code, 200)

    def test_expense_and_reimbursement_are_private_and_queued_for_both_transports(self):
        path = f'commissioning/{self.project.pk}/expenses/'
        creation = self.request(self.a, 'post', path, {'amount': '140', 'description': 'Запчасти'})
        self.assertEqual(creation.status_code, 201)
        confirm = f"{path}{creation.data['id']}/reimburse/"
        self.assertEqual(self.request(self.admin, 'post', confirm).status_code, 200)
        events = NotificationInbox.objects.filter(event_type='commissioning_action').order_by('id')
        self.assertEqual(list(events.values_list('user_id', 'kind')), [
            (self.admin.pk, 'expense_created'), (self.a.pk, 'expense_reimbursed'),
        ])
        self.assertEqual(events.filter(commissioning_push_after__isnull=False).count(), 2)
        group = 'notifications/?category=commissioning&group_commissioning=1'
        self.assertEqual(self.request(self.a, 'get', group).data['results'][0]['kind'], 'expense_reimbursed')
        self.assertEqual(self.request(self.b, 'get', group).data['results'], [])
        self.assertEqual(self.request(self.admin, 'get', 'notifications/?category=ordinary&group_commissioning=1').data['results'], [])

    def test_foreign_tenant_rejected_and_unassigned_adjuster_read_only(self):
        uri = f'commissioning/{self.project.pk}/'
        self.assertIn(self.request(self.stranger, 'get', uri).status_code, (403, 404))
        self.assertIn(self.request(self.a, 'get', uri, tenant=self.foreign).status_code, (403, 404))
        User = get_user_model()
        outsider = User.objects.create_user(username='unassigned-13', password='VeryStrong13Password!')
        Membership.objects.create(user=outsider, organization=self.org, role='ADJUSTER', can_commissioning=True)
        self.assertEqual([p['id'] for p in self.request(outsider, 'get', 'commissioning/').data], [self.project.pk])
        self.assertEqual(self.request(outsider, 'get', uri).status_code, 200)

    def test_all_projects_visible_but_unassigned_writes_are_denied(self):
        other = CommissioningProject.objects.create(organization=self.org, name='Другой объект', address='Второй 2')
        lift = CommissioningLift.objects.create(project=other, label='Чужой лифт', progress=40)
        CommissioningAssignment.objects.create(lift=lift, user=self.b)
        CommissioningProgress.objects.create(lift=lift, actor=self.b, before=0, after=40, description='Настроены двери')
        foreign = CommissioningProject.objects.create(organization=self.foreign, name='Чужая организация', address='Третий 3')
        rows = self.request(self.a, 'get', 'commissioning/').data
        self.assertEqual({row['id'] for row in rows}, {self.project.pk, other.pk})
        base = f'commissioning/{other.pk}/'
        detail = self.request(self.a, 'get', base).data
        self.assertFalse(detail['can_write'])
        self.assertFalse(detail['lifts'][0]['can_edit'])
        self.assertEqual(detail['lifts'][0]['history'][0]['description'], 'Настроены двери')
        for endpoint, body in (
            (f'lifts/{lift.pk}/progress/', {'revision': 0, 'progress': 70, 'description': 'Подмена'}),
            ('needs/', {'description': 'Общий вопрос'}),
            ('extra-work/', {'description': 'Работа', 'price': '10'}),
            ('lift-requests/', {'label': 'Новый лифт'}),
            ('expenses/', {'amount': '10', 'description': 'Расход'}),
            ('sync/', {'id': str(uuid4()), 'type': 'expense', 'body': {'amount': '10', 'description': 'Офлайн'}}),
            ('sync/', {'id': str(uuid4()), 'type': 'progress', 'body': {'lift': lift.pk, 'revision': 0, 'progress': 70, 'description': 'Подмена'}}),
        ):
            response = self.request(self.a, 'post', base+endpoint, body)
            self.assertEqual(response.status_code, 403, (endpoint, response.data))
        lift.refresh_from_db()
        self.assertEqual(lift.progress, 40)
        self.assertFalse(other.needs.exists())
        self.assertFalse(other.extras.exists())
        self.assertFalse(other.lift_requests.exists())
        self.assertFalse(other.expenses.exists())
        # An assignment grants writes; revocation keeps read access and removes writes.
        assignment = CommissioningAssignment.objects.create(lift=lift, user=self.a)
        self.assertTrue(self.request(self.a, 'get', base).data['can_write'])
        assignment.active = False
        assignment.save(update_fields=['active'])
        self.assertFalse(self.request(self.a, 'get', base).data['can_write'])
        Membership.objects.filter(user=self.a, organization=self.org).update(can_commissioning=False)
        self.assertEqual(self.request(self.a, 'get', base).status_code, 403)
        self.assertIn(self.request(self.b, 'get', f'commissioning/{foreign.pk}/').status_code, (403, 404))

    def test_external_adjuster_cannot_read_regular_workflow_or_staff(self):
        for endpoint in ('tickets/', 'tasks/', 'chat/', 'parts/', 'media/', 'organizations/members/'):
            response = self.request(self.a, 'get', endpoint)
            self.assertEqual(response.status_code, 403, endpoint)
        profile = self.request(self.a, 'get', 'me/')
        self.assertEqual(profile.status_code, 200)
        self.assertTrue(profile.data['commissioning_only'])
        self.assertFalse(profile.data['can_create_ticket'])
        self.assertEqual(self.request(self.a, 'get', 'organizations/').status_code, 200)
        Membership.objects.filter(user=self.a, organization=self.org).update(active=False)
        self.assertEqual(self.request(self.a, 'get', f'commissioning/{self.project.pk}/').status_code, 403)

    def test_external_adjuster_account_can_be_created_without_technician(self):
        row = self.request(self.admin, 'post', 'organizations/members/create/', {
            'username': 'external-worker-13',
            'full_name': 'Наладчик Проверка',
            'password': 'UniqueStrongPassword13!',
            'role': 'ADJUSTER',
        })
        self.assertEqual(row.status_code, 201, row.data)
        self.assertIsNone(row.data['technician'])
        membership = Membership.objects.get(
            organization=self.org, user__username='external-worker-13')
        self.assertEqual(membership.role, 'ADJUSTER')
        self.assertIsNone(membership.technician)

    def test_assignment_can_explicitly_add_adjuster_role_to_existing_mechanic(self):
        mechanic = get_user_model().objects.create_user(username='dual-role-mechanic')
        card = Technician.objects.create(organization=self.org, full_name='Механик на объекте')
        member = Membership.objects.create(organization=self.org, user=mechanic, technician=card)
        other_card = Technician.objects.create(organization=self.foreign, full_name='Совместитель')
        other_membership = Membership.objects.create(
            organization=self.foreign, user=mechanic, technician=other_card)
        candidates = 'commissioning/assignees/'
        path = f'commissioning/{self.project.pk}/lifts/{self.lift_a.pk}/assign/'
        progress = f'commissioning/{self.project.pk}/lifts/{self.lift_a.pk}/progress/'

        listing = self.request(self.admin, 'get', candidates)
        self.assertEqual(listing.status_code, 200)
        self.assertIn({'user': mechanic.pk, 'name': card.full_name, 'role': 'MECHANIC',
                       'can_commissioning': False}, listing.data)
        self.assertIn(self.a.pk, [row['user'] for row in listing.data])
        summary = self.request(self.admin, 'get', 'commissioning/').data[0]
        self.assertEqual(summary['unassigned_count'], 0)
        extra_lift = CommissioningLift.objects.create(project=self.project, label='Без исполнителя')
        self.assertEqual(self.request(self.admin, 'get', 'commissioning/').data[0]['unassigned_count'], 1)
        self.assertNotIn('unassigned_count', self.request(self.a, 'get', 'commissioning/').data[0])
        extra_lift.delete()
        self.assertNotIn(self.stranger.pk, [row['user'] for row in listing.data])
        self.assertEqual(self.request(self.a, 'get', candidates).status_code, 403)
        self.assertEqual(self.request(self.admin, 'post', path, {'user': mechanic.pk}).status_code, 400)
        body = {'user': mechanic.pk, 'grant_commissioning': True}
        self.assertEqual(self.request(self.a, 'post', path, body).status_code, 403)
        self.assertEqual(self.request(self.admin, 'post', path,
                                      body | {'user': self.stranger.pk}).status_code, 404)
        member.refresh_from_db()
        self.assertFalse(member.can_commissioning)
        self.assertFalse(CommissioningAssignment.objects.filter(lift=self.lift_a, user=mechanic).exists())

        for _ in range(2):
            response = self.request(self.admin, 'post', path, body)
            self.assertEqual(response.status_code, 200, response.data)
        member.refresh_from_db()
        other_membership.refresh_from_db()
        self.assertEqual((member.role, member.technician_id), ('MECHANIC', card.pk))
        self.assertTrue(member.can_commissioning)
        self.assertFalse(other_membership.can_commissioning)
        self.assertEqual(CommissioningAssignment.objects.filter(lift=self.lift_a, user=mechanic).count(), 1)
        profile = self.request(mechanic, 'get', 'me/').data
        self.assertFalse(profile['commissioning_only'])
        self.assertTrue(profile['can_commissioning'])
        self.assertEqual(self.request(mechanic, 'get', 'tickets/').status_code, 200)
        self.assertEqual(self.request(mechanic, 'post', progress, {
            'revision': 0, 'progress': 10, 'description': 'Проверка дверей',
        }).status_code, 200)

        card.active = False
        card.save(update_fields=['active'])
        self.assertNotIn(mechanic.pk, [row['user'] for row in self.request(self.admin, 'get', candidates).data])
        self.assertEqual(self.request(self.admin, 'post', path, body).status_code, 404)

    def test_approval_requests_and_archiving_are_audited(self):
        p = self.project.pk
        created = self.request(self.a, 'post', f'commissioning/{p}/extra-work/',
            {'price': '1200.00', 'description': 'Перенос станции'})
        self.assertEqual(created.status_code, 201)
        extra_id = created.data['id']
        self.assertEqual(CommissioningExtraWork.objects.get(pk=extra_id).status, 'PENDING')
        self.assertEqual(self.request(self.a, 'post', f'commissioning/{p}/extra-work/{extra_id}/decision/',
            {'approve': True}).status_code, 403)
        self.assertEqual(self.request(self.admin, 'post', f'commissioning/{p}/extra-work/{extra_id}/decision/',
            {'approve': True}).status_code, 200)
        requested = self.request(self.a, 'post', f'commissioning/{p}/lift-requests/',
            {'label': 'Лифт В'})
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(self.request(self.admin, 'post',
            f'commissioning/{p}/lift-requests/{requested.data["id"]}/decision/',
            {'approve': True}).status_code, 200)
        self.assertEqual(CommissioningLift.objects.filter(project=self.project).count(), 3)
        self.assertEqual(self.request(self.admin, 'post', f'commissioning/{p}/archive/',
            {'reason': 'Объект закончен'}).status_code, 200)
        self.assertEqual(self.request(self.a, 'post', f'commissioning/{p}/needs/',
            {'description': 'После архива'}).status_code, 400)
        self.assertEqual(self.request(self.a, 'get', f'commissioning/{p}/').status_code, 200)

    def test_offline_progress_replays_without_duplicate_and_rechecks_assignment(self):
        path = f'commissioning/{self.project.pk}/sync/'
        command = {'id': str(uuid4()), 'type': 'progress', 'body': {
            'lift': self.lift_a.pk, 'revision': 0, 'progress': 34, 'description': 'Осмотр',
        }}
        first = self.request(self.a, 'post', path, command)
        self.assertEqual(first.status_code, 201, first.data)
        replay = self.request(self.a, 'post', path, command)
        self.assertTrue(replay.data['replayed'])
        self.assertEqual(first.data['result'], replay.data['result'])
        self.assertEqual(CommissioningProgress.objects.filter(lift=self.lift_a).count(), 1)
        command['body']['progress'] = 89
        self.assertEqual(self.request(self.a, 'post', path, command).status_code, 409)
        CommissioningAssignment.objects.filter(lift=self.lift_a, user=self.a).update(active=False)
        self.assertEqual(self.request(self.a, 'post', path, command).status_code, 403)

    def test_revoking_module_permission_preserves_assignment_and_hides_project(self):
        member = Membership.objects.get(user=self.a, organization=self.org)
        self.assertEqual(self.request(self.a, 'get', 'commissioning/').status_code, 200)
        self.client.force_authenticate(self.admin)
        result = self.client.patch(
            f'/api/organizations/members/{member.pk}/', {'can_commissioning': False},
            format='json', HTTP_X_ORGANIZATION_ID=str(self.org.pk),
        )
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(self.request(self.a, 'get', 'me/').data['can_commissioning'])
        self.assertEqual(self.request(self.a, 'get', 'commissioning/').status_code, 403)
        self.assertTrue(CommissioningAssignment.objects.filter(lift=self.lift_a, user=self.a).exists())

    def test_offline_expense_and_receipt_commit_together_without_duplicates(self):
        import json

        path = f'commissioning/{self.project.pk}/sync/'
        command = json.dumps({'id': str(uuid4()), 'type': 'expense', 'body': {
            'lift': self.lift_a.pk, 'spent_on': '2026-11-10',
            'amount': '210.35', 'description': 'Клеммы',
        }})
        stream = io.BytesIO()
        Image.new('RGB', (8, 8)).save(stream, format='PNG')
        for n in range(2):
            photo = SimpleUploadedFile('receipt.png', stream.getvalue(), content_type='image/png')
            result = self.request(self.a, 'post', path, {'command': command, 'receipt': photo},
                                  format='multipart')
            self.assertEqual(result.status_code, 201 if not n else 200, result.data)
        self.assertEqual(CommissioningExpense.objects.count(), 1)
        expense = CommissioningExpense.objects.get()
        self.assertEqual(expense.spent_on.isoformat(), '2026-11-10')
        self.assertTrue(expense.receipt.storage.exists(expense.receipt.name))
        url = f'commissioning/{self.project.pk}/expenses/{expense.pk}/receipt/'
        self.assertEqual(self.request(self.b, 'get', url).status_code, 403)
        downloaded = self.request(self.admin, 'get', url)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded['Content-Type'], 'image/png')


    def test_archived_project_chat_and_photos_are_hidden_but_progress_remains(self):
        def photo():
            out = io.BytesIO()
            Image.new('RGB', (8, 8), 'green').save(out, 'PNG')
            return SimpleUploadedFile('photo.png', out.getvalue(), content_type='image/png')

        base = f'commissioning/{self.project.pk}/'
        outsider = get_user_model().objects.create_user(username='not-in-project')
        Membership.objects.create(organization=self.org, user=outsider, role='DISPATCHER', can_commissioning=True)
        with atomic_media():
            old_message = CommissioningMessage.objects.create(
                project=self.project, author=self.a, text='Старое сообщение',
            )
            chat_photo = CommissioningPhoto.objects.create(
                message=old_message, asset=ingest(self.a, photo(), organization=self.org),
            )
        uri = base+f'photos/{chat_photo.pk}/'
        self.assertEqual(self.request(self.a, 'get', base).data['messages'], [])
        self.assertEqual(self.request(self.admin, 'get', base).data['messages'], [])
        self.assertEqual(self.request(self.b, 'get', uri+'preview/').status_code, 404)
        self.assertEqual(self.request(outsider, 'get', uri).status_code, 404)
        self.assertEqual(self.request(self.stranger, 'get', uri, tenant=self.foreign).status_code, 404)
        self.assertEqual(self.request(self.admin, 'get', f'media/{chat_photo.asset_id}/download/').status_code, 404)
        self.assertEqual(self.request(self.b, 'get', 'commissioning/chat/').data, [])
        self.assertEqual(self.request(self.a, 'post', base+'messages/', {'text': 'Новое'}).status_code, 410)
        self.assertEqual(self.request(self.a, 'post', base+'sync/', {
            'id': str(uuid4()), 'type': 'message', 'body': {'text': 'Офлайн'},
        }).status_code, 410)
        self.assertEqual(list(CommissioningMessage.objects.values_list('pk', flat=True)), [old_message.pk])
        self.assertEqual(CommissioningPhoto.objects.get(pk=chat_photo.pk).message_id, old_message.pk)
        self.assertFalse(NotificationInbox.objects.exists())

        progress = base+f'lifts/{self.lift_a.pk}/progress/'
        result = self.request(self.a, 'post', progress, {
            'revision': '0', 'progress': '25', 'description': 'Проверка дверей', 'photos': photo(),
        }, format='multipart')
        self.assertEqual(result.status_code, 200, result.data)
        progress_photo = CommissioningPhoto.objects.get(progress_id=result.data['event'])
        progress_uri = base+f'photos/{progress_photo.pk}/'
        self.assertEqual(self.request(self.admin, 'get', progress_uri).status_code, 200)
        self.assertEqual(self.request(self.a, 'get', progress_uri).status_code, 200)
        self.assertEqual(self.request(self.b, 'get', progress_uri).status_code, 200)
        detail = self.request(self.b, 'get', base).data
        self.assertEqual(len(detail['lifts'][0]['history'][0]['photos']), 1)
        self.assertEqual(set(NotificationInbox.objects.filter(event_type='commissioning_progress').values_list('user_id',flat=True)),
                         {self.admin.pk})
        CommissioningAssignment.objects.filter(lift=self.lift_b, user=self.b).update(active=False)
        self.assertEqual(self.request(self.b, 'get', 'notifications/').data['results'], [])
        self.assertEqual(self.request(self.b, 'get', uri).status_code, 404)

    def test_invalid_second_photo_rolls_back_team_chat_and_notification(self):
        out = io.BytesIO()
        Image.new('RGB', (5, 5), 'blue').save(out, 'PNG')
        response = self.request(self.a, 'post', 'commissioning/chat/', {
            'body': 'Проверка',
            'photos': [SimpleUploadedFile('valid.png', out.getvalue(), content_type='image/png'),
                       SimpleUploadedFile('invalid.png', b'not an image', content_type='image/png')],
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CommissioningMessage.objects.exists())
        self.assertFalse(CommissioningPhoto.objects.exists())
        self.assertFalse(NotificationInbox.objects.exists())
