"""Tests for persistent notification feed, tenant isolation and read semantics."""
from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import (Organization, Membership, NotificationInbox,
                     CommissioningProject, CommissioningLift, CommissioningAssignment)


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.get(pk=1)
        self.foreign=Organization.objects.create(name='Вторая')
        User=get_user_model()
        self.user=User.objects.create_user(username='notice-a13',password='VeryStrongPass13!')
        self.other=User.objects.create_user(username='notice-b13',password='VeryStrongPass13!')
        self.adjuster=User.objects.create_user(username='notice-c13',password='VeryStrongPass13!')
        Membership.objects.create(organization=self.org,user=self.user,role='ADMIN')
        Membership.objects.create(organization=self.org,user=self.other,role='ADMIN')
        Membership.objects.create(organization=self.org,user=self.adjuster,role='ADJUSTER', can_commissioning=True)
        self.client=APIClient()

    def request(self,user,method,path,body=None):
        self.client.force_authenticate(user)
        kwargs={'HTTP_X_ORGANIZATION_ID':str(self.org.pk)}
        if method=='GET':
            return self.client.get('/api/'+path,**kwargs)
        return self.client.post('/api/'+path,body or {},format='json',**kwargs)

    def test_read_own_and_filter_unread(self):
        own=NotificationInbox.objects.create(organization=self.org,user=self.user,
            event_type='ticket',event_id=100,kind='created',title='Заявка №100',
            target_type='ticket',target_id=100)
        NotificationInbox.objects.create(organization=self.org,user=self.other,
            event_type='ticket',event_id=100,kind='created',title='Заявка №100',
            target_type='ticket',target_id=100)
        rows=self.request(self.user,'GET','notifications/')
        self.assertEqual(rows.status_code,200)
        self.assertEqual(rows.data['unread'],1)
        self.assertEqual(len(rows.data['results']),1)
        forbidden=self.request(self.other,'POST',f'notifications/{own.pk}/read/')
        self.assertEqual(forbidden.status_code,404)
        seen=self.request(self.user,'POST',f'notifications/{own.pk}/read/')
        self.assertEqual(seen.status_code,200)
        self.assertEqual(self.request(self.user,'GET','notifications/?unread=1').data['unread'],0)
        self.assertEqual(self.request(self.user,'GET','notifications/?unread=1').data['results'],[])
        self.assertEqual(self.request(self.user,'POST',f'notifications/{own.pk}/read/').status_code,200)

    def test_history_paginates_with_global_counts_and_hides_routine_statuses(self):
        for event_id in range(1, 38):
            NotificationInbox.objects.create(
                organization=self.org, user=self.user, event_type='ticket', event_id=event_id,
                kind='created', title='Заявка', target_type='ticket', target_id=event_id,
                is_entrapment=event_id == 37,
            )
        NotificationInbox.objects.create(
            organization=self.org, user=self.user, event_type='ticket', event_id=38,
            kind='accepted', title='Статус', target_type='ticket', target_id=1, is_entrapment=True,
        )
        path = 'notifications/?category=ordinary&limit=30'
        first = self.request(self.user, 'GET', path).data
        self.assertEqual(len(first['results']), 30)
        next_page = self.request(self.user, 'GET', f"{path}&before={first['next_before']}").data
        self.assertEqual([row['target_id'] for row in next_page['results']], [6, 5, 4, 3, 2, 1])
        self.assertEqual(next_page['unread_by_category'], {'ordinary': 36, 'entrapment': 1})
        self.assertIsNone(next_page['next_before'])
        self.assertEqual(self.request(self.user, 'GET', path + '&before=-1').status_code, 400)

    def test_opened_push_marks_only_its_own_event_in_the_active_organization(self):
        for user, event, company in (
            (self.user, 100, self.org), (self.user, 101, self.org),
            (self.other, 100, self.org), (self.user, 102, self.foreign),
        ):
            NotificationInbox.objects.create(
                organization=company, user=user, event_type='ticket', event_id=event,
                kind='created', title='Заявка', target_type='ticket', target_id=10,
                is_entrapment=event == 100,
            )
        opened = {'target': 'ticket', 'target_id': 10, 'event_id': 100}
        self.assertEqual(self.request(self.user, 'POST', 'notifications/read-push/',
                                      {**opened, 'target_id': 11}).data, {'updated': 0})
        self.assertEqual(self.request(self.user, 'POST', 'notifications/read-push/',
                                      {**opened, 'event_id': 102}).data, {'updated': 0})
        self.assertEqual(self.request(self.user, 'POST', 'notifications/read-push/', opened).data,
                         {'updated': 1})
        self.assertEqual(self.request(self.user, 'POST', 'notifications/read-push/', opened).data,
                         {'updated': 0})
        counts = self.request(self.user, 'GET', 'notifications/counts/').data
        self.assertEqual((counts['unread'], counts['entrapment'], counts['sections']['tickets']),
                         (1, 0, 1))
        self.assertEqual(NotificationInbox.objects.filter(read_at__isnull=True).count(), 3)
        self.assertEqual(len(self.request(self.user, 'GET', 'notifications/').data['results']), 2)

    def test_role_change_hides_prior_regular_notifications_from_adjuster(self):
        old=NotificationInbox.objects.create(organization=self.org,user=self.adjuster,
            event_type='ticket',event_id=800,kind='created',
            title='Заявка №800',target_type='ticket',target_id=800)
        shown=NotificationInbox.objects.create(organization=self.org,user=self.adjuster,
            event_type='commissioning_message',event_id=801,kind='message',
            title='Объект наладки',target_type='commissioning',target_id=801)
        # Restricted roles cannot read historic operational notifications.
        response=self.request(self.adjuster,'GET','notifications/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['results'],[])
        self.assertEqual(self.request(self.adjuster,'POST',f'notifications/{old.pk}/read/').status_code,404)
        self.assertEqual(self.request(self.adjuster,'POST',f'notifications/{shown.pk}/read/').status_code,404)

    def test_foreign_org_not_visible_even_to_same_user(self):
        NotificationInbox.objects.create(organization=self.foreign,user=self.user,
            event_type='ticket',event_id=200,kind='created',
            title='Чужая',target_type='ticket',target_id=200)
        self.assertEqual(self.request(self.user,'GET','notifications/').data['results'],[])

    def test_archived_project_chat_never_counts_or_appears_in_inbox(self):
        project = CommissioningProject.objects.create(
            organization=self.org, name='Объект', address='Тестовая 1', created_by=self.user,
        )
        lift = CommissioningLift.objects.create(project=project, label='№1')
        CommissioningAssignment.objects.create(lift=lift, user=self.adjuster)
        for recipient in (self.other, self.adjuster):
            archived = NotificationInbox.objects.create(
                organization=self.org, user=recipient, event_type='commissioning_message',
                event_id=801, kind='message', title='Сообщение на объекте',
                target_type='commissioning', target_id=project.pk,
            )
            self.assertEqual(self.request(recipient, 'GET', 'notifications/').data['results'], [])
            counts = self.request(recipient, 'GET', 'notifications/counts/').data
            self.assertEqual((counts['unread'], counts['sections']['commissioning']), (0, 0))
            self.assertEqual(self.request(recipient, 'POST',
                                          f'notifications/{archived.pk}/read/').status_code, 404)
        self.assertEqual(NotificationInbox.objects.filter(event_type='commissioning_message').count(), 2)

    def test_team_chat_is_shared_without_project_assignments_and_scoped_by_access(self):
        unprivileged = get_user_model().objects.create_user(username='without-commissioning')
        Membership.objects.create(organization=self.org, user=unprivileged, role='DISPATCHER')
        Membership.objects.create(organization=self.foreign, user=self.adjuster, role='ADJUSTER',
                                  can_commissioning=True)
        with TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            image = BytesIO()
            Image.new('RGB', (12, 12), 'orange').save(image, 'PNG')
            operation_id = str(uuid4())
            self.client.force_login(self.user)
            def send_photo(text):
                attachment = SimpleUploadedFile('test.png', image.getvalue(), content_type='image/png')
                return self.client.post('/api/commissioning/chat/',
                                        {'body': text, 'photos': attachment, 'operation_id': operation_id},
                                        format='multipart', HTTP_X_ORGANIZATION_ID=str(self.org.pk))

            sent = send_photo('Общий вопрос')
            self.assertEqual(sent.status_code, 201, sent.data)
            message_id = sent.data['id']
            repeated = send_photo('Общий вопрос')
            self.assertEqual((repeated.status_code, repeated.data), (200, {'id': message_id}))
            self.assertEqual(send_photo('Другое сообщение').status_code, 409)
            history = self.request(self.adjuster, 'GET', 'commissioning/chat/')
            self.assertEqual([row['body'] for row in history.data], ['Общий вопрос'])
            photo = history.data[0]['attachments'][0]['url']
            self.assertEqual(self.client.get(photo).status_code, 200)
            self.assertEqual(self.request(unprivileged, 'GET', 'commissioning/chat/').status_code, 403)
            self.assertEqual(self.client.get(photo).status_code, 403)
            self.assertEqual(self.request(unprivileged, 'GET', 'notifications/counts/').data['unread'], 0)
            self.client.force_authenticate(self.adjuster)
            foreign = {'HTTP_X_ORGANIZATION_ID': str(self.foreign.pk)}
            self.assertEqual(self.client.get('/api/commissioning/chat/', **foreign).data, [])
            self.assertEqual(self.client.get(f'/api/commissioning/chat/{message_id}/', **foreign).status_code, 404)
            self.assertEqual(self.client.get(photo, **foreign).status_code, 404)

        newer = self.request(self.other, 'POST', 'commissioning/chat/', {'body': 'Ответ'})
        inbox = self.request(self.adjuster, 'GET', 'notifications/').data
        self.assertEqual(inbox['unread'], 2)
        self.assertEqual(inbox['results'][0]['preview'], 'Ответ')
        updated = self.request(self.adjuster, 'POST', 'notifications/read-chat/',
                               {'target': 'commissioning_chat', 'through': message_id}).data
        self.assertEqual(updated['updated'], 1)
        counts = self.request(self.adjuster, 'GET', 'notifications/counts/').data
        self.assertEqual((counts['unread'], counts['commissioning_chat'], counts['sections']['commissioning']),
                         (1, 1, 1))
        self.assertEqual(self.request(self.other, 'GET', 'notifications/counts/').data['unread'], 1)
        remaining = self.request(self.adjuster, 'GET', 'notifications/?unread=1').data['results']
        self.assertEqual([item['target_id'] for item in remaining], [newer.data['id']])
        self.assertEqual(self.request(self.adjuster, 'POST', f'notifications/{remaining[0]["id"]}/read/').status_code, 200)
        counts = self.request(self.adjuster, 'GET', 'notifications/counts/').data
        self.assertEqual((counts['unread'], counts['commissioning_chat'], counts['sections']['commissioning']),
                         (0, 0, 0))
        self.assertEqual(len(self.request(self.adjuster, 'GET', 'notifications/').data['results']), 2)
        Membership.objects.filter(organization=self.org, user=self.adjuster).update(can_commissioning=False)
        self.assertEqual(self.request(self.adjuster, 'GET', 'notifications/counts/').data['unread'], 0)
        self.assertEqual(self.request(self.adjuster, 'GET',
                                      f'commissioning/chat/{newer.data["id"]}/').status_code, 403)


    def test_read_all_spans_pages_and_categories_but_not_other_people_or_employers(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Building,Ticket
        home=Building.objects.create(organization=self.org,name='Дом',address='Адрес')
        ticket=Ticket.objects.create(organization=self.org,building=home,title='Не менять состояние',status='NEW')
        rows=[]
        for i in range(36):
            rows.append(NotificationInbox.objects.create(organization=self.org,user=self.user,event_type='ticket',event_id=10000+i,kind='created',title='Входящее',target_type='ticket',target_id=ticket.pk,is_entrapment=i==0))
        other=NotificationInbox.objects.create(organization=self.org,user=self.other,event_type='ticket',event_id=10000,kind='created',title='Чужое',target_type='ticket',target_id=ticket.pk)
        foreign=NotificationInbox.objects.create(organization=self.foreign,user=self.user,event_type='ticket',event_id=40000,kind='created',title='Другой работодатель',target_type='ticket',target_id=1)
        hidden=NotificationInbox.objects.create(organization=self.org,user=self.user,event_type='ticket',event_id=30000,kind='accepted',title='Скрытое',target_type='ticket',target_id=ticket.pk)
        old=timezone.now()-timedelta(days=1)
        read=NotificationInbox.objects.create(organization=self.org,user=self.user,event_type='ticket',event_id=30001,kind='created',title='Уже прочитано',target_type='ticket',target_id=ticket.pk,read_at=old)
        result=self.request(self.user,'POST','notifications/read-all/')
        self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['updated'],36)
        self.assertIn('no-store',result['Cache-Control'])
        self.assertFalse(NotificationInbox.objects.filter(pk__in=[r.pk for r in rows],read_at__isnull=True).exists())
        for untouched in (other,foreign,hidden):
            untouched.refresh_from_db();self.assertIsNone(untouched.read_at)
        read.refresh_from_db();self.assertEqual(read.read_at,old)
        ticket.refresh_from_db();self.assertEqual(ticket.status,'NEW')
        self.assertFalse(NotificationInbox.objects.filter(pk__in=[r.pk for r in rows],message_read_at__isnull=False).exists())
        self.assertEqual(self.request(self.user,'POST','notifications/read-all/').data['updated'],0)
        self.assertEqual(self.request(self.user,'GET','notifications/counts/').data['unread'],0)

    def test_read_all_does_not_clear_a_later_arrival(self):
        from unittest.mock import patch
        from django.db.models.query import QuerySet
        first=NotificationInbox.objects.create(organization=self.org,user=self.user,event_type='team_message',event_id=70001,kind='message',title='Первое',target_type='chat',target_id=70001)
        original=QuerySet.update;later=[]
        def update(query,**values):
            if query.model is NotificationInbox and 'read_at' in values and not later:
                later.append(NotificationInbox.objects.create(organization=self.org,user=self.user,event_type='team_message',event_id=70002,kind='message',title='Новое',target_type='chat',target_id=70002))
            return original(query,**values)
        with patch.object(QuerySet,'update',new=update):
            response=self.request(self.user,'POST','notifications/read-all/')
        self.assertEqual(response.status_code,200,response.data)
        first.refresh_from_db();later[0].refresh_from_db()
        self.assertIsNotNone(first.read_at);self.assertIsNone(later[0].read_at)
        self.assertEqual(self.request(self.user,'GET','notifications/counts/').data['unread'],1)

    def test_read_all_requires_membership_and_cookie_csrf(self):
        browser=APIClient(enforce_csrf_checks=True);browser.force_login(self.user)
        self.assertEqual(browser.post('/api/notifications/read-all/',{},format='json').status_code,403)
        profile=browser.get('/api/me/').data
        self.assertEqual(browser.post('/api/notifications/read-all/',{},format='json',HTTP_X_CSRFTOKEN=profile['csrf']).status_code,200)
        self.assertEqual(self.request(self.user,'GET','notifications/read-all/').status_code,405)
        Membership.objects.filter(user=self.user).update(active=False)
        self.assertEqual(self.request(self.user,'POST','notifications/read-all/').status_code,403)
