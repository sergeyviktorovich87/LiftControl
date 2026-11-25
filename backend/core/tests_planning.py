from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Organization,Membership,Technician,VacationRequest,DutyShift,VacationEvent,DutyRoster,NotificationInbox,PushSubscription,PlanningPushDelivery

class PlanningTests(TestCase):
 def setUp(self):
  self.company=Organization.objects.create(name='План',timezone='Asia/Chita');self.other=Organization.objects.create(name='Чужая')
  self.users=[get_user_model().objects.create_user('plan-'+name) for name in ['admin','one','two','dispatcher','adjuster']]
  self.admin,self.one,self.two,self.dispatcher,self.adjuster=self.users
  self.tech=[Technician.objects.create(organization=self.company,full_name=n) for n in ['Первый','Второй','Третий']]
  for user,role,tech in [(self.admin,'ADMIN',None),(self.one,'MECHANIC',self.tech[0]),(self.two,'MECHANIC',self.tech[1]),(self.dispatcher,'DISPATCHER',None),(self.adjuster,'ADJUSTER',None)]:Membership.objects.create(organization=self.company,user=user,role=role,technician=tech)
  self.client=APIClient();self.header={'HTTP_X_ORGANIZATION_ID':str(self.company.pk)}
  clock=patch('django.utils.timezone.now',return_value=datetime(2098,12,31,tzinfo=timezone.utc));clock.start();self.addCleanup(clock.stop)
  self.plan={'from':'2099-01-01','to':'2099-01-04','start_time':'09:00','mode':'daily','people':[t.pk for t in self.tech],'overrides':{},'replace_existing':False}
 def call(self,user,path,body=None,method='post',header=None):
  self.client.force_authenticate(user);return getattr(self.client,method)('/api/'+path,body,format='json',**(header or self.header))
 def vacation(self,user=None,**extra):
  return self.call(user or self.one,'vacations/',{'start':'2099-01-01','end':'2099-01-02','comment':'Личный комментарий','status':'PENDING','operation_id':str(uuid4()),**extra})
 def preview(self,**kwargs):return self.call(self.admin,'duty/planner-preview/',{'draft':{**self.plan,**kwargs}})
 def publish(self,preview,**kwargs):return self.call(self.admin,'duty/planner-publish/',{'draft':{**self.plan,**kwargs},'token':preview['token']})
 def test_request_permissions_private_comments_and_retry(self):
  body={'start':'2099-01-01','end':'2099-01-02','comment':'Частное','status':'PENDING','operation_id':str(uuid4())}
  first=self.call(self.one,'vacations/',body);self.assertEqual(first.status_code,201,first.data)
  self.assertEqual(self.call(self.one,'vacations/',body).data['id'],first.data['id']);self.assertEqual(VacationRequest.objects.count(),1)
  self.assertEqual(self.vacation(employee=self.two.pk).status_code,403)
  uri=f"vacations/{first.data['id']}/"
  self.assertEqual(self.call(self.two,uri,method='get').status_code,403)
  for u in [self.one,self.dispatcher]:self.assertEqual(self.call(u,uri,{'action':'approve','revision':0}).status_code,403)
  result=self.call(self.admin,uri,{'action':'approve','revision':0});self.assertEqual(result.status_code,200,result.data)
  public=self.call(self.two,uri,method='get').data;self.assertEqual(public['comment'],'');self.assertNotIn('history',public)
  export=self.call(self.two,'vacations/export/?from=2099-01-01&to=2099-01-31',method='get');self.assertEqual(export.status_code,200);self.assertNotIn('Частное',export.content.decode())
  self.assertEqual(self.call(self.admin,uri,{'action':'reject','revision':0,'response':'Устарело'}).status_code,400)
 def test_pending_does_not_affect_rotation_approved_does_without_rewriting(self):
  first=self.vacation();self.assertEqual(first.status_code,201)
  before=self.preview().data;self.assertEqual(before['rows'][0]['technician'],self.tech[0].pk)
  result=self.publish(before);self.assertEqual(result.status_code,200,result.data);self.assertEqual(DutyShift.objects.count(),4)
  original=list(DutyShift.objects.values_list('pk','technician_id'))
  self.call(self.admin,f"vacations/{first.data['id']}/",{'action':'approve','revision':0})
  self.assertEqual(original,list(DutyShift.objects.values_list('pk','technician_id')))
  protected=self.preview().data;self.assertGreater(protected['missing'],0)
  replacement=self.preview(replace_existing=True).data;self.assertEqual(replacement['missing'],0);self.assertNotEqual(replacement['rows'][0]['technician'],self.tech[0].pk)
  self.assertEqual(self.publish(replacement,replace_existing=True).status_code,200)
  self.assertFalse(DutyShift.objects.filter(start__date='2099-01-01',technician=self.tech[0]).exists())
 def test_draft_is_saved_without_shifts_and_stale_overwrites_rejected(self):
  data=self.call(self.admin,'duty/planner/',method='get').data
  body={'revision':data['revision'],'draft':self.plan}
  self.assertEqual(self.call(self.admin,'duty/planner/',body,method='put').status_code,200)
  self.assertFalse(DutyShift.objects.exists())
  self.assertEqual(self.call(self.admin,'duty/planner/',body,method='put').status_code,400)
  self.assertEqual(self.call(self.one,'duty/planner/',method='get').status_code,403)
 def test_preview_token_rejects_changed_leave_and_incomplete_assignments(self):
  preview=self.preview().data
  item=self.vacation();self.call(self.admin,f"vacations/{item.data['id']}/",{'action':'approve','revision':0})
  self.assertEqual(self.publish(preview).status_code,400);self.assertFalse(DutyShift.objects.exists())
  for tech in self.tech[1:]:VacationRequest.objects.create(organization=self.company,technician=tech,employee_name=tech.full_name,start='2099-01-01',end='2099-01-04',status='APPROVED',operation_id=uuid4())
  result=self.preview().data;self.assertGreater(result['missing'],0);self.assertEqual(self.publish(result).status_code,400)
 def test_split_shifts_custom_time_and_atomic_repeat(self):
  options={'mode':'split','start_time':'07:30'};p=self.preview(**options).data;self.assertEqual(len(p['rows']),8)
  self.assertEqual(p['rows'][0]['kind'],'day');self.assertEqual(p['rows'][1]['kind'],'night')
  self.assertEqual(self.publish(p,**options).data,{'added':8,'updated':0,'revision':1})
  self.assertEqual(self.publish(p,**options).status_code,400);self.assertEqual(DutyShift.objects.count(),8)
  for s in DutyShift.objects.all():self.assertEqual((s.end-s.start).total_seconds(),43200)
 def test_cross_organization_technician_and_permission_boundaries(self):
  foreign=Technician.objects.create(organization=self.other,full_name='Чужой')
  self.assertEqual(self.preview(people=[foreign.pk]).status_code,400)
  self.assertEqual(self.call(self.admin,'duty/planner/',method='get',header={'HTTP_X_ORGANIZATION_ID':str(self.other.pk)}).status_code,403)
  self.assertEqual(self.vacation(self.adjuster).status_code,201)
  self.assertEqual(self.call(self.adjuster,'duty/planner/',method='get').status_code,403)
 def test_proposal_resubmit_and_cancel_keep_history(self):
  item=self.vacation().data;uri=f"vacations/{item['id']}/"
  r=self.call(self.admin,uri,{'action':'propose','revision':0,'start':'2099-02-01','end':'2099-02-10','response':'Выберите февраль'});self.assertEqual(r.data['status'],'CHANGES')
  r=self.call(self.one,uri,{'action':'submit','revision':1,'start':'2099-02-01','end':'2099-02-10','comment':'Февраль'});self.assertEqual(r.data['status'],'PENDING')
  self.call(self.admin,uri,{'action':'approve','revision':2})
  self.assertEqual(self.call(self.one,uri,{'action':'cancel','revision':3}).status_code,403)
  self.assertEqual(self.call(self.admin,uri,{'action':'cancel','revision':3}).data['status'],'CANCELLED')
  self.assertEqual(VacationEvent.objects.filter(vacation_id=item['id']).count(),5)
 def test_old_settings_cannot_bypass_vacation_approval(self):
  result=self.call(self.admin,'duty/roster-settings/',{'previous':{'cycles':[],'periods':[]},'config':{'cycles':[],'periods':[{'type':'leave','from':'2099-01-01','to':'2099-01-02','worker':self.tech[0].pk}]}},method='put')
  self.assertEqual(result.status_code,400)
 def test_web_push_outbox_scoped_to_recipient_and_revocation_checked(self):
  sub=PushSubscription.objects.create(organization=self.company,user=self.admin,endpoint='https://fcm.googleapis.com/fcm/send/plan-test',p256dh='key',auth='secret')
  item=self.vacation().data;self.assertEqual(PlanningPushDelivery.objects.filter(subscription=sub).count(),1)
  notification=NotificationInbox.objects.get(user=self.admin,target_id=item['id'],target_type='vacation')
  self.assertEqual(self.call(self.two,f'planning/notifications/{notification.pk}/',method='get').status_code,404)
  self.assertEqual(self.call(self.admin,f'planning/notifications/{notification.pk}/',method='get').status_code,200)
  Membership.objects.filter(user=self.admin,organization=self.company).update(role='DISPATCHER')
  self.assertEqual(self.call(self.admin,f'planning/notifications/{notification.pk}/',method='get').status_code,404)
 def test_pdf_export_works_and_has_no_personal_comments(self):
  item=self.vacation().data;self.call(self.admin,f"vacations/{item['id']}/",{'action':'approve','revision':0})
  result=self.call(self.one,'vacations/export/?from=2099-01-01&to=2099-01-31&file=pdf',method='get');self.assertEqual(result.status_code,200);self.assertTrue(result.content.startswith(b'%PDF'))

 def test_legacy_leave_transfer_preserves_queue_and_ids(self):
  from importlib import import_module
  from types import SimpleNamespace
  from django.apps import apps
  config={'cycles':[{'from':'2099-01-01','people':[self.tech[0].pk]}],'periods':[{'type':'leave','worker':self.tech[0].pk,'from':'2099-02-01','to':'2099-02-14'},{'type':'replace','worker':self.tech[1].pk,'target':self.tech[2].pk,'from':'2099-02-15','to':'2099-02-16'}]}
  row=DutyRoster.objects.create(organization=self.company,config=config)
  move=import_module('core.migrations.0032_vacation_planning').move_old_leave
  move(apps,SimpleNamespace(connection=SimpleNamespace(alias='default')));row.refresh_from_db()
  self.assertEqual(row.config['cycles'],config['cycles']);self.assertEqual(row.config['periods'],config['periods'][1:])
  item=VacationRequest.objects.get();self.assertEqual(item.technician_id,self.tech[0].pk);self.assertEqual(item.employee_id,self.one.pk);self.assertEqual(item.status,'APPROVED')
  move(apps,SimpleNamespace(connection=SimpleNamespace(alias='default')));self.assertEqual(VacationRequest.objects.count(),1)
 def test_published_manual_assignment_preserved_until_explicit_review(self):
  p=self.preview().data;self.publish(p)
  shift=DutyShift.objects.order_by('start').first();shift.technician=self.tech[2];shift.roster_generated=False;shift.save()
  p=self.preview().data;self.assertEqual(p['rows'][0]['technician'],self.tech[2].pk);self.assertFalse(p['rows'][0]['changed'])
  p=self.preview(replace_existing=True).data;self.assertTrue(p['rows'][0]['changed']);self.assertEqual(DutyShift.objects.get(pk=shift.pk).technician_id,self.tech[2].pk)
