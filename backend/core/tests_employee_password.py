from datetime import timedelta
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuditEvent, EmployeePasswordSetup, Membership, Organization


class EmployeePasswordSetupTests(TestCase):
    password = 'UniqueEmployeeTest-4097!phrase'
    setup_path = '/employee-password/'
    members_path = '/api/organizations/members/'

    def setUp(self):
        self.organization = Organization.objects.get(pk=1)
        self.other = Organization.objects.create(name='Другая организация')
        self.owner = get_user_model().objects.create_user('setup-owner')
        Membership.objects.create(user=self.owner, organization=self.organization, role='ADMIN')
        Membership.objects.create(user=self.owner, organization=self.other, role='DIRECTOR')
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        self.browser = Client(enforce_csrf_checks=True)

    def create_employee(self, role='MECHANIC'):
        response = self.api.post(self.members_path + 'create/', {
            'username': 'pending-worker', 'full_name': 'Новый Механик',
            'role': role, 'can_commissioning': True,
        }, format='json', secure=True)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def redeem(self, token, password=None, confirmation=None, **request_options):
        secret = self.browser.cookies['csrftoken'].value
        password = self.password if password is None else password
        return self.browser.post(self.setup_path, {
            'token': token, 'new_password1': password,
            'new_password2': password if confirmation is None else confirmation,
            'csrfmiddlewaretoken': secret,
        }, **({'secure': True, 'HTTP_ORIGIN': 'https://testserver'} | request_options))

    def test_first_password_unlocks_existing_web_and_mobile_login_once(self):
        response = self.create_employee()
        url = urlsplit(response['setup_url'])
        self.assertEqual((url.scheme, url.path, url.query), ('https', self.setup_path, ''))
        self.assertTrue(response['password_setup_pending'])
        member = Membership.objects.get(pk=response['id'])
        self.assertTrue(member.can_commissioning)
        self.assertEqual(member.technician.full_name, 'Новый Механик')
        self.assertFalse(member.user.has_usable_password())
        self.assertFalse(self.browser.login(username=member.user.username, password=self.password))
        self.assertNotEqual(member.password_setup.token_hash, url.fragment)

        opened = self.browser.get(url.path, secure=True)
        self.assertEqual(opened.status_code, 200)
        self.assertIn('no-store', opened.headers['Cache-Control'])
        self.assertEqual(opened.headers['Referrer-Policy'], 'same-origin')
        self.assertNotContains(opened, url.fragment)
        self.assertEqual(self.browser.post(url.path, {'token': url.fragment}, secure=True).status_code, 403)
        self.assertEqual(self.redeem(url.fragment, confirmation='different').status_code, 400)
        self.assertEqual(self.redeem(url.fragment, password='short').status_code, 400)
        self.assertEqual(self.redeem(url.fragment, password='long!'+('a'*1024)).status_code, 400)
        self.assertContains(self.redeem(url.fragment), 'Пароль установлен.')
        self.assertEqual(self.redeem(url.fragment, password='Another-Strong-Candidate!').status_code, 400)

        self.assertFalse(EmployeePasswordSetup.objects.filter(membership=member).exists())
        self.assertTrue(self.browser.login(username=member.user.username, password=self.password))
        login = APIClient().post('/api/mobile/login/', {
            'username': member.user.username, 'password': self.password, 'device_name': 'Тестовый телефон',
        }, format='json', secure=True)
        self.assertEqual(login.status_code, 200, login.content)
        listing = self.api.get(self.members_path, secure=True)
        self.assertNotContains(listing, url.fragment)
        self.assertFalse(next(row for row in listing.json() if row['id'] == member.pk)['password_setup_pending'])
        audit = AuditEvent.objects.filter(action__startswith='employee.password_setup')
        self.assertEqual(set(audit.values_list('action', flat=True)), {
            'employee.password_setup_issued', 'employee.password_setup_completed',
        })
        self.assertNotIn(url.fragment, str(list(audit.values_list('details', flat=True))))
        self.assertNotIn(self.password, str(list(audit.values_list('details', flat=True))))

    def test_expired_links_and_reissue_respect_organization_and_access(self):
        response = self.create_employee()
        old_token = urlsplit(response['setup_url']).fragment
        member_id = response['id']
        member_path = f'{self.members_path}{member_id}/'
        reissue_path = member_path + 'password-setup/'
        self.browser.get(self.setup_path, secure=True)
        EmployeePasswordSetup.objects.filter(membership_id=member_id).update(
            expires_at=timezone.now()-timedelta(seconds=1),
        )
        self.assertEqual(self.redeem(old_token).status_code, 400)
        self.assertEqual(self.api.post(
            reissue_path, secure=True, HTTP_X_ORGANIZATION_ID=str(self.other.pk),
        ).status_code, 404)
        replacement = self.api.post(reissue_path, secure=True)
        self.assertEqual(replacement.status_code, 200)
        token = urlsplit(replacement.json()['setup_url']).fragment
        self.assertNotEqual(token, old_token)
        self.assertEqual(self.redeem(old_token).status_code, 400)

        self.assertEqual(self.api.patch(member_path, {'active': False}, format='json').status_code, 200)
        self.assertEqual(self.redeem(token).status_code, 400)
        self.assertEqual(self.api.post(reissue_path, secure=True).status_code, 400)
        self.assertEqual(self.api.patch(member_path, {'active': True}, format='json').status_code, 200)
        self.assertEqual(self.redeem(token).status_code, 400)
        token = urlsplit(self.api.post(reissue_path, secure=True).json()['setup_url']).fragment
        self.assertContains(self.redeem(token), 'Пароль установлен.')
        self.assertEqual(self.api.post(reissue_path, secure=True).status_code, 400)

    @override_settings(DEBUG=False)
    def test_insecure_setup_and_link_from_former_issuer_are_rejected(self):
        response = self.create_employee(role='ADMIN')
        token = urlsplit(response['setup_url']).fragment
        self.assertEqual(self.browser.get(self.setup_path).status_code, 403)
        self.browser.get(self.setup_path, secure=True)
        Membership.objects.filter(user=self.owner, organization=self.organization).update(role='DIRECTOR')
        self.assertEqual(self.redeem(token).status_code, 400)
        self.assertEqual(self.api.post(
            f"{self.members_path}{response['id']}/password-setup/", secure=True,
        ).status_code, 403)
