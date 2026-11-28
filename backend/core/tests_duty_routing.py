from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from . import tests_field_ops as fixture
from .models import DutyShift, Ticket, Membership, Building, AuditEvent


class DutyRoutingTests(fixture.TestCase):
    setUp=fixture.FieldOperationsTests.setUp
    login=fixture.FieldOperationsTests.login

    def shift(self, **values):
        now=timezone.now()
        return DutyShift.objects.create(organization=self.org,technician=self.second,
            start=values.pop('start',now-timedelta(hours=1)),end=values.pop('end',now+timedelta(hours=1)),**values)

    def create(self, **values):
        return self.client.post('/api/tickets/',{'building':self.lift.building_id,'elevator':self.lift.pk,
            'title':'Проверить двери','description':'Поступила заявка',**values},format='json')

    def setting(self,shift,mode,stamp=None):
        return self.client.post(f'/api/duty/{shift.pk}/assignment/',{'assignment_mode':mode,
            'expected_updated_at':stamp or shift.updated_at.isoformat()},format='json')

    def test_every_priority_explicit_other_assignment_and_unknown_lift_follow_duty(self):
        self.lift.assigned_technician=self.tech;self.lift.save()
        shift=self.shift(assignment_mode='DUTY')
        for priority in Ticket.Priority.values:
            result=self.create(priority=priority,assigned_to=self.tech.pk)
            self.assertEqual(result.status_code,201,result.data)
            self.assertEqual(result.data['assigned_to'],self.second.pk)
        result=self.create(elevator=None)
        self.assertEqual(result.status_code,201,result.data);self.assertEqual(result.data['assigned_to'],self.second.pk)
        self.assertEqual(self.client.get('/api/me/').data['duty_shift']['assignment_mode'],'DUTY')
        rows=self.client.get('/api/duty/roster/',{'from':shift.start.date().isoformat(),'to':shift.end.date().isoformat()}).data
        self.assertEqual(next(s for day in rows for s in day['shifts'] if s['id']==shift.pk)['assignment_mode'],'DUTY')

    def test_regular_mode_end_boundary_and_existing_tickets_are_unchanged(self):
        self.lift.assigned_technician=self.tech;self.lift.save()
        shift=self.shift()
        first=self.create();self.assertEqual(first.data['assigned_to'],self.tech.pk)
        result=self.setting(shift,'DUTY');self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(Ticket.objects.get(pk=first.data['id']).assigned_to_id,self.tech.pk)
        self.assertEqual(self.create().data['assigned_to'],self.second.pk)
        with patch('core.ticket_flow.timezone.now',return_value=shift.end):
            self.assertEqual(self.create().data['assigned_to'],self.tech.pk)
        shift.refresh_from_db()
        self.assertEqual(self.setting(shift,'LIFT').status_code,200)
        self.assertEqual(self.create().data['assigned_to'],self.tech.pk)

    def test_permissions_tenant_stale_completed_invalid_and_revocation(self):
        shift=self.shift()
        self.login(self.worker);self.assertEqual(self.setting(shift,'DUTY').status_code,403)
        self.login(self.owner,self.other);self.assertEqual(self.setting(shift,'DUTY').status_code,404)
        self.login(self.owner)
        self.assertEqual(self.setting(shift,'wrong').status_code,400)
        self.assertEqual(self.setting(shift,'DUTY').status_code,200)
        self.assertEqual(self.setting(shift,'LIFT').status_code,409)
        self.assertTrue(AuditEvent.objects.filter(action='duty.assignment').exists())
        DutyShift.objects.filter(pk=shift.pk).update(end=timezone.now()-timedelta(seconds=1))
        shift.refresh_from_db();self.assertEqual(self.setting(shift,'LIFT').status_code,400)
        Membership.objects.filter(user=self.owner,organization=self.org).update(active=False)
        self.assertEqual(self.setting(shift,'DUTY').status_code,403)

    def test_pending_handover_preserves_mode_and_routes_only_future_tickets(self):
        self.lift.assigned_technician=self.second;self.lift.save()
        shift=self.shift()
        self.login(self.colleague)
        pending=self.client.post(f'/api/duty/{shift.pk}/swap/',{'technician':self.tech.pk,'reason':'Нужна подмена'},format='json')
        self.assertEqual(pending.status_code,201,pending.data)
        self.login(self.owner)
        self.assertEqual(self.setting(shift,'DUTY').status_code,200)
        old=self.create();self.assertEqual(old.data['assigned_to'],self.second.pk)
        self.login(self.worker)
        response=self.client.post(f'/api/duty-swaps/{pending.data["id"]}/accept/',{},format='json')
        self.assertEqual(response.status_code,200,response.data)
        replacement=DutyShift.objects.exclude(pk=shift.pk).get(organization=self.org)
        self.assertEqual(replacement.assignment_mode,'DUTY')
        self.login(self.owner)
        self.assertEqual(self.create().data['assigned_to'],self.tech.pk)
        self.assertEqual(Ticket.objects.get(pk=old.data['id']).assigned_to_id,self.second.pk)

    def test_ineligible_duty_fails_without_silent_fallback(self):
        self.shift(assignment_mode='DUTY')
        Membership.objects.filter(user=self.colleague,organization=self.org).update(active=False)
        self.assertEqual(self.create().status_code,400)
        self.assertEqual(Ticket.objects.count(),0)

    def test_offline_replay_uses_same_routing_and_is_idempotent(self):
        import uuid
        self.shift(assignment_mode='DUTY')
        op={'id':str(uuid.uuid4()),'type':'create','occurred_at':timezone.now().isoformat(),'body':{
            'building':self.lift.building_id,'elevator':self.lift.pk,'title':'Офлайн заявка','description':'Проверить двери'}}
        result=self.client.post('/api/mobile/sync/',op,format='json');self.assertEqual(result.status_code,201,result.data)
        self.assertEqual(result.data['ticket']['assigned_to'],self.second.pk)
        replay=self.client.post('/api/mobile/sync/',op,format='json');self.assertEqual(replay.status_code,200,replay.data)
        self.assertEqual(replay.data['ticket']['id'],result.data['ticket']['id'])

    def test_repair_marker_permissions_validation_and_entrapment_guard(self):
        result=self.create(assigned_to=self.tech.pk)
        pk=result.data['id']
        url=f'/api/tickets/{pk}/mark-repair/'
        self.login(self.colleague)
        self.assertEqual(self.client.post(url,{'reason':'Требуется ремонт'},format='json').status_code,403)
        self.login(self.owner,self.other)
        self.assertEqual(self.client.post(url,{'reason':'Требуется ремонт'},format='json').status_code,404)
        self.login(self.owner)
        self.assertEqual(self.client.post(url,{'reason':' '},format='json').status_code,400)
        marked=self.client.post(url,{'reason':'Требуется замена платы'},format='json')
        self.assertEqual(marked.status_code,200,marked.data)
        self.assertEqual(marked.data['status'],'NEW')
        urgent=self.create(priority='ENTRAPMENT')
        self.assertEqual(self.client.post(f'/api/tickets/{urgent.data["id"]}/mark-repair/',{'reason':'Обход освобождения'},format='json').status_code,400)

    def test_legacy_republication_preserves_shift_routing(self):
        from datetime import datetime,time
        from zoneinfo import ZoneInfo
        day=timezone.now().date()+timedelta(days=3)
        start=datetime.combine(day,time(9),ZoneInfo(self.org.timezone))
        shift=self.shift(start=start,end=start+timedelta(days=1),assignment_mode='DUTY')
        body={'from':day.isoformat(),'to':day.isoformat(),'time':'09:00','hours':24,'technicians':[self.tech.pk],'replace':True}
        preview=self.client.post('/api/duty/preview/',body,format='json')
        self.assertEqual(preview.status_code,200,preview.data)
        result=self.client.post('/api/duty/apply/',{'token':preview.data['token']},format='json')
        self.assertEqual(result.status_code,200,result.data)
        new=DutyShift.objects.get(organization=self.org,start=start)
        self.assertEqual((new.assignment_mode,new.technician_id),('DUTY',self.tech.pk))
