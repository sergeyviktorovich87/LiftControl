from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditEvent, DutyShift, Membership, Organization, Technician


class RosterTests(TestCase):
    def setUp(self):
        self.company = Organization.objects.create(name='Дежурства', timezone='Asia/Yakutsk')
        self.other = Organization.objects.create(name='Другая')
        self.admin = get_user_model().objects.create_user('roster-admin')
        self.worker = get_user_model().objects.create_user('roster-mechanic')
        self.people = [Technician.objects.create(organization=self.company, full_name=name)
                       for name in ('Первый', 'Второй', 'Третий')]
        self.one, self.two, self.three = [row.pk for row in self.people]
        Membership.objects.create(user=self.admin, organization=self.company, role='ADMIN')
        Membership.objects.create(user=self.worker, organization=self.company,
                                  role='MECHANIC', technician_id=self.one)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.header = {'HTTP_X_ORGANIZATION_ID': str(self.company.pk)}
        self.config = {'cycles': [{'from': '2099-01-01', 'people': [self.one, self.two]}], 'periods': []}
        clock = patch('django.utils.timezone.now', return_value=datetime(2098, 12, 31, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)

    def settings(self, config, previous=None):
        return self.client.put('/api/duty/roster-settings/', {
            'config': config, 'previous': previous or {'cycles': [], 'periods': []},
        }, format='json', **self.header)

    def roster(self, start, end):
        return self.client.get('/api/duty/roster/', {'from': start, 'to': end}, **self.header)

    def publish(self):
        return self.client.post('/api/duty/roster-publish/', {'from': '2099-01-01', 'to': '2099-01-31'},
                                format='json', **self.header)

    def test_rotation_crosses_month_and_temporary_period_does_not_move_base(self):
        self.config['periods'] = [
            {'type': 'temp', 'from': '2099-01-31', 'to': '2099-02-01', 'people': [self.three]},
            {'type': 'replace', 'from': '2099-02-02', 'to': '2099-02-02', 'worker': self.one, 'target': self.three},
        ]
        result = self.settings(self.config)
        self.assertEqual(result.status_code, 200, result.content)
        rows = self.roster('2099-01-30', '2099-02-03').json()
        self.assertEqual([row['suggested'] for row in rows], [self.two, self.three, self.three, self.three, self.two])
        self.assertTrue(rows[3]['replacement'])
        self.assertEqual(DutyShift.objects.count(), 0)

    def test_publication_is_atomic_preserves_manual_edits_and_retries_safely(self):
        self.config['periods'] = [{'type':'leave','from':'2099-01-03','to':'2099-01-03','worker':self.one}]
        self.assertEqual(self.settings(self.config).status_code, 200)
        self.assertEqual(self.publish().status_code, 400)
        self.assertEqual(DutyShift.objects.count(), 0)
        day = self.roster('2099-01-03','2099-01-03').json()[0]
        self.assertIn(self.one, day['unavailable'])
        request = {'start':day['start'],'end':day['end'],'kind':'daily','technician':self.one}
        self.assertEqual(self.client.post('/api/duty/', request, format='json', **self.header).status_code, 400)
        request['technician'] = self.three
        result = self.client.post('/api/duty/', request, format='json', **self.header)
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(self.publish().json(), {'added': 30, 'updated': 0})
        self.assertEqual(self.publish().json(), {'added': 0, 'updated': 0})
        shift = DutyShift.objects.get(pk=result.json()['id'])
        self.assertEqual(shift.technician_id, self.three)
        self.assertFalse(shift.roster_generated)
        self.assertEqual(AuditEvent.objects.filter(action='duty.roster.publish').count(), 1)
        self.assertEqual(self.settings(self.config).status_code, 400)

    def test_mechanic_cannot_read_draft_or_write_settings(self):
        self.assertEqual(self.settings(self.config).status_code, 200)
        self.client.force_authenticate(self.worker)
        self.assertIsNone(self.roster('2099-01-01', '2099-01-01').json()[0]['suggested'])
        self.assertEqual(self.client.get('/api/duty/roster-settings/', **self.header).status_code, 403)
        self.assertEqual(self.publish().status_code, 403)
        self.assertEqual(self.client.get('/api/duty/roster/', {'from':'2099-01-01','to':'2099-01-01'},
            HTTP_X_ORGANIZATION_ID=str(self.other.pk)).status_code, 403)
