"""0.13 maintenance PDF tests: tenant, signed-in access and six-column report."""
from datetime import datetime, timezone as utc_timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Organization, Membership, Building, Elevator, Technician, Maintenance, Ticket


class MaintenancePdfTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.get(pk=1)
        self.other = Organization.objects.create(name='Вторая организация')
        User = get_user_model()
        self.admin = User.objects.create_user(username='pdf-admin-13',password='StrongSecretPwd13!')
        self.foreign_admin = User.objects.create_user(username='pdf-foreign-13',password='StrongSecretPwd13!')
        self.adjuster = User.objects.create_user(username='pdf-adjuster-13',password='StrongSecretPwd13!')
        Membership.objects.create(organization=self.organization,user=self.admin,role='ADMIN')
        Membership.objects.create(organization=self.other,user=self.foreign_admin,role='ADMIN')
        Membership.objects.create(organization=self.organization,user=self.adjuster,role='ADJUSTER')
        self.building = Building.objects.create(organization=self.organization,name='Первый',
                                                address='Улица 1')
        self.elevator = Elevator.objects.create(organization=self.organization,
                                                building=self.building,factory_number='TO-13')
        self.tech=Technician.objects.create(organization=self.organization,
                                            full_name='Иванов Иван',role='MECHANIC')
        self.entry=Maintenance.objects.create(organization=self.organization,
                        elevator=self.elevator,technician=self.tech,kind='TO1',
                        planned_date=timezone.localdate(),completed_at=timezone.now(),
                        notes='Проверка башмаков и дверей')
        self.client=APIClient()

    def url(self):
        return f'/api/maintenance/{self.elevator.pk}/journal/pdf/'

    def get(self,user,query=None,org=None):
        self.client.force_authenticate(user)
        return self.client.get(self.url(),query or {},
                               HTTP_X_ORGANIZATION_ID=str((org or self.organization).pk))

    def test_pdf_download_has_valid_header_and_is_not_cached(self):
        response=self.get(self.admin)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(response['Content-Type'],'application/pdf')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertGreater(len(response.content),1000)

    def test_no_cross_organization_or_adjuster_download(self):
        self.assertIn(self.get(self.foreign_admin,org=self.other).status_code,(403,404))
        self.assertEqual(self.get(self.adjuster).status_code,403)

    def test_period_validation(self):
        self.assertEqual(self.get(self.admin,{'from':'nonsense'}).status_code,400)
        self.assertEqual(self.get(self.admin,{'from':'2027-02-02','to':'2027-01-01'}).status_code,400)
        self.assertEqual(self.get(self.admin,{'from':'2027-01-01','to':'2027-01-02'}).status_code,200)

    def test_period_uses_local_date_of_organization(self):
        self.organization.timezone = 'Asia/Chita'
        self.organization.save(update_fields=['timezone'])
        self.entry.completed_at = datetime(2026, 11, 13, 15, 30, tzinfo=utc_timezone.utc)
        self.entry.save(update_fields=['completed_at'])
        with patch('core.maintenance_pdf._pdf', return_value=b'%PDF-') as render:
            result = self.get(self.admin, {'from': '2026-11-14', 'to': '2026-11-14'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual([row['source_id'] for row in render.call_args.args[1]], [self.entry.pk])


    def test_journal_and_pdf_use_same_completed_work_for_lift(self):
        self.organization.timezone = 'Asia/Chita'
        self.organization.save(update_fields=['timezone'])
        completed_at = datetime(2026, 11, 13, 15, 30, tzinfo=utc_timezone.utc)
        self.entry.completed_at = completed_at
        self.entry.planned_date = datetime(2026, 11, 5).date()
        self.entry.save(update_fields=['completed_at', 'planned_date'])
        ticket_date = completed_at.replace(hour=16)
        common = dict(organization=self.organization, elevator=self.elevator,
                      assigned_to=self.tech, completed_at=ticket_date)
        ticket = Ticket.objects.create(**common, status=Ticket.Status.DONE, title='Неисправность',
                                       repair='Заменён ролик двери')
        Ticket.objects.create(**common, status=Ticket.Status.CANCELED, title='Отменённая')
        Ticket.objects.create(**common, status=Ticket.Status.IN_PROGRESS, title='В работе')
        Ticket.objects.create(organization=self.organization, elevator=self.elevator,
                              status=Ticket.Status.DONE, title='Нет даты выполнения')
        other_lift = Elevator.objects.create(organization=self.organization,
                                             building=self.building, factory_number='OTHER')
        Ticket.objects.create(organization=self.organization, elevator=other_lift,
                              status=Ticket.Status.DONE, title='Другой лифт', completed_at=ticket_date)
        Maintenance.objects.create(organization=self.organization, elevator=self.elevator,
                                   planned_date=datetime(2026, 11, 14).date(), notes='В плане')
        filters = {'from': '2026-11-14', 'to': '2026-11-14'}
        self.client.force_authenticate(self.admin)
        endpoint = self.url().replace('pdf/', '')
        response = self.client.get(endpoint, filters, HTTP_X_ORGANIZATION_ID=str(self.organization.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        rows = response.json()['rows']
        self.assertEqual([(row['source'], row['source_id']) for row in rows],
                         [('maintenance', self.entry.pk), ('ticket', ticket.pk)])
        self.assertEqual([row['date'] for row in rows], ['2026-11-14', '2026-11-14'])
        self.assertIn('ТО-1', rows[0]['description'])
        self.assertIn('Заменён ролик двери', rows[1]['description'])
        self.assertEqual(rows[1]['performer'], 'Иванов Иван / Механик')
        with patch('core.maintenance_pdf._pdf', return_value=b'%PDF-') as render:
            self.assertEqual(self.get(self.admin, filters).status_code, 200)
            self.assertEqual(render.call_args.args[1], rows)
        self.client.force_authenticate(self.foreign_admin)
        self.assertEqual(self.client.get(endpoint, HTTP_X_ORGANIZATION_ID=str(self.other.pk)).status_code, 404)
        self.client.force_authenticate(self.adjuster)
        self.assertEqual(self.client.get(endpoint, HTTP_X_ORGANIZATION_ID=str(self.organization.pk)).status_code, 403)
