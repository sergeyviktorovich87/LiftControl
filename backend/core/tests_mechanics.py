from datetime import timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Organization, Membership, Technician, Building, Elevator, Ticket, DutyShift, VacationRequest, AuditEvent

class MechanicDirectoryTests(TestCase):
 def setUp(self):
  self.org=Organization.objects.create(name='Команда',timezone='Asia/Chita');self.other=Organization.objects.create(name='Чужая')
  self.a=Technician.objects.create(organization=self.org,full_name='Алексеев Алексей');self.b=Technician.objects.create(organization=self.org,full_name='Борисов Владимир')
  self.archived=Technician.objects.create(organization=self.org,full_name='Архивный',active=False)
  self.foreign=Technician.objects.create(organization=self.other,full_name='Чужой механик')
  self.admin=get_user_model().objects.create_user('mechanic-admin');self.worker=get_user_model().objects.create_user('mechanic-worker');self.dispatcher=get_user_model().objects.create_user('mechanic-dispatcher');self.adjuster=get_user_model().objects.create_user('mechanic-adjuster')
  for user,role,tech in [(self.admin,'ADMIN',None),(self.worker,'MECHANIC',self.a),(self.dispatcher,'DISPATCHER',None),(self.adjuster,'ADJUSTER',None)]:Membership.objects.create(user=user,organization=self.org,role=role,technician=tech)
  self.building=Building.objects.create(organization=self.org,name='Дом',address='УЛИЦА ЦЕНТРАЛЬНАЯ, 12')
  self.foreign_building=Building.objects.create(organization=self.other,name='Другой',address='ЧУЖОЙ АДРЕС')
  self.lifts=[Elevator.objects.create(organization=self.org,building=self.building,assigned_technician=self.a,entrance=str(i),inventory_number='LC-'+str(i)) for i in range(1,28)]
  self.free=Elevator.objects.create(organization=self.org,building=self.building,inventory_number='FREE')
  self.foreign_lift=Elevator.objects.create(organization=self.other,building=self.foreign_building,assigned_technician=self.foreign,inventory_number='FOREIGN')
  self.client=APIClient();self.header={'HTTP_X_ORGANIZATION_ID':str(self.org.pk)}
 def call(self,user,path,body=None,method='get',header=None):
  self.client.force_authenticate(user);return getattr(self.client,method)('/api/'+path,body,format='json',**(header or self.header))
 def changes(self,*items,user=None):return self.call(user or self.admin,f'mechanics/{self.a.pk}/assignments/',{'changes':list(items)},method='post')
 def test_counts_use_only_real_current_duty_approved_vacation_and_in_work(self):
  now=timezone.now();DutyShift.objects.create(organization=self.org,technician=self.a,start=now-timedelta(hours=1),end=now+timedelta(hours=1))
  day=now.astimezone(__import__('zoneinfo').ZoneInfo(self.org.timezone)).date()
  VacationRequest.objects.create(organization=self.org,technician=self.b,employee_name='Борисов',start=day,end=day,status='APPROVED',operation_id=uuid4(),comment='Не раскрывать')
  VacationRequest.objects.create(organization=self.org,technician=self.a,employee_name='Алексеев',start=day,end=day,status='PENDING',operation_id=uuid4())
  for status in ['IN_PROGRESS','STOPPED','LONG_REPAIR','NEW','DONE','CANCELED']:Ticket.objects.create(organization=self.org,elevator=self.lifts[0],assigned_to=self.a,title='Заявка',status=status)
  result=self.call(self.worker,'mechanics/overview/');self.assertEqual(result.status_code,200,result.data)
  by={r['id']:r for r in result.data};self.assertEqual(by[self.a.pk]['status'],'DUTY');self.assertEqual(by[self.a.pk]['in_work'],3);self.assertEqual(by[self.a.pk]['lift_count'],27);self.assertEqual(by[self.b.pk]['status'],'VACATION');self.assertNotIn(self.archived.pk,by);self.assertNotIn('Не раскрывать',str(result.data))
  self.assertEqual(len(self.call(self.worker,'mechanics/overview/?include_archived=1').data),3)
 def test_lifts_are_paginated_naturally_searched_and_filtered(self):
  self.lifts[0].stopped_at=timezone.now();self.lifts[0].save()
  result=self.call(self.worker,f'mechanics/{self.a.pk}/lifts/').data
  self.assertEqual((result['total'],result['matched'],result['pages'],len(result['items'])),(27,27,2,25));self.assertEqual([r['entrance'] for r in result['items'][:3]],['1','2','3']);self.assertEqual(result['items'][0]['building_lift_count'],27)
  self.assertEqual(len(self.call(self.worker,f'mechanics/{self.a.pk}/lifts/?page=2').data['items']),2)
  query=self.call(self.worker,f'mechanics/{self.a.pk}/lifts/?q=центральная&status=stopped').data;self.assertEqual(query['matched'],1)
  self.lifts[-1].active=False;self.lifts[-1].save();self.assertEqual(self.call(self.worker,f'mechanics/{self.a.pk}/lifts/').data['total'],26)
  self.assertEqual(self.call(self.worker,f'mechanics/{self.a.pk}/lifts/?include_archived=1').data['total'],27)
 def test_tenant_and_adjuster_boundaries(self):
  for suffix in ['lifts/','lifts/export/']:
   self.assertEqual(self.call(self.worker,f'mechanics/{self.foreign.pk}/'+suffix).status_code,404)
  self.assertEqual(self.call(self.adjuster,'mechanics/overview/').status_code,403)
  self.assertEqual(self.call(self.admin,'mechanics/overview/',header={'HTTP_X_ORGANIZATION_ID':str(self.other.pk)}).status_code,403)
 def test_transfer_requires_admin_and_matching_previous_assignment(self):
  change={'elevator':self.lifts[0].pk,'previous':self.a.pk,'technician':self.b.pk}
  for user in [self.worker,self.dispatcher,self.adjuster]:self.assertEqual(self.changes(change,user=user).status_code,403)
  result=self.changes(change);self.assertEqual(result.status_code,200,result.data);self.assertEqual(result.data['updated'],1)
  self.assertEqual(self.changes(change).status_code,400);self.lifts[0].refresh_from_db();self.assertEqual(self.lifts[0].assigned_technician_id,self.b.pk)
  self.assertEqual(AuditEvent.objects.filter(action='mechanic.assignments').count(),1)
 def test_batch_is_atomic_and_rejects_foreign_inactive_and_duplicates(self):
  good={'elevator':self.free.pk,'previous':None,'technician':self.a.pk}
  stale={'elevator':self.lifts[0].pk,'previous':self.b.pk,'technician':self.a.pk}
  self.assertEqual(self.changes(good,stale).status_code,400);self.free.refresh_from_db();self.assertIsNone(self.free.assigned_technician_id)
  for dest in [self.foreign.pk,self.archived.pk]:self.assertEqual(self.changes({'elevator':self.lifts[0].pk,'previous':self.a.pk,'technician':dest}).status_code,400)
  self.assertEqual(self.changes(good,good).status_code,400)
  self.assertEqual(self.changes({'elevator':self.foreign_lift.pk,'previous':self.foreign.pk,'technician':self.a.pk}).status_code,400)
 def test_add_remove_and_pdf_without_mutating_other_records(self):
  self.assertEqual(self.changes({'elevator':self.free.pk,'previous':None,'technician':self.a.pk}).status_code,200)
  self.assertEqual(self.changes({'elevator':self.free.pk,'previous':self.a.pk,'technician':None}).status_code,200)
  result=self.call(self.worker,f'mechanics/{self.a.pk}/lifts/export/?q=LC-1');self.assertEqual(result.status_code,200);self.assertTrue(result.content.startswith(b'%PDF'));self.assertEqual(result['Cache-Control'],'private, no-store');self.assertEqual(Elevator.objects.filter(organization=self.org,assigned_technician=self.a).count(),27)
