from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Organization, Membership, AuditEvent
from .system_updates import ACTION, recent_request


class SystemUpdateTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('server_owner',password='test-password')
        self.admin=get_user_model().objects.create_user('company_admin',password='test-password')
        self.org=Organization.objects.first()
        Membership.objects.create(user=self.admin,organization=self.org,role='ADMIN')
        self.client=APIClient()
        self.status={'state':'available','target':'0.13.18','request_id':0,'reachable':True}

    @patch('core.system_updates.read_status')
    def test_only_global_owner_and_exact_release(self,status):
        status.return_value=self.status
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/updates/system/').status_code,403)
        self.assertEqual(self.client.post('/api/updates/system/',{'action':'check'},format='json').status_code,403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/api/updates/system/').status_code,200)
        for payload in ({'action':'shell'},{'action':'install','target':'0.13.19'},
                        {'action':'install','target':'0.13.18','command':'arbitrary'}):
            self.assertEqual(self.client.post('/api/updates/system/',payload,format='json').status_code,400)
        response=self.client.post('/api/updates/system/',{'action':'install','target':'0.13.18'},format='json')
        self.assertEqual(response.status_code,202,response.content)
        self.assertEqual(recent_request().pk,response.json()['request_id'])
        self.assertEqual(AuditEvent.objects.filter(action=ACTION).count(),1)
        self.assertEqual(self.client.post('/api/updates/system/',{'action':'check'},format='json').status_code,400)
        self.owner.is_superuser=False
        self.owner.save(update_fields=['is_superuser'])
        self.assertIsNone(recent_request())

    @patch('core.system_updates.read_status')
    def test_csrf_required_and_unavailable(self,status):
        status.return_value=self.status
        client=APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post('/api/updates/system/',{'action':'check'},format='json').status_code,403)
        self.client.force_login(self.owner)
        status.return_value=None
        self.assertEqual(self.client.post('/api/updates/system/',{'action':'check'},format='json').status_code,400)
