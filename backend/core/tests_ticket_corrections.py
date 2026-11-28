from datetime import timedelta
from django.utils import timezone
from . import tests_field_ops as fixture
from .models import Ticket, DutyShift, Membership, TicketEvent


class TicketCorrectionTests(fixture.TestCase):
    setUp = fixture.FieldOperationsTests.setUp
    login = fixture.FieldOperationsTests.login

    def ticket(self, **values):
        return Ticket.objects.create(organization=self.org, building=self.lift.building,
            elevator=self.lift, assigned_to=self.tech, created_by=self.owner,
            title='Ошибка в описании', **values)

    def correct(self, ticket, **values):
        return self.client.post(f'/api/tickets/{ticket.pk}/correct/', {
            'title':'Исправленное название', 'reason':'Ошибся при вводе',
            'expected_updated_at':ticket.updated_at.isoformat(), **values}, format='json')

    def test_manager_corrects_all_states_without_changing_work_and_preserves_history(self):
        for state in ('NEW','IN_PROGRESS','STOPPED','LONG_REPAIR','DONE','CANCELED'):
            ticket=self.ticket(status=state, priority='ENTRAPMENT', repair='Результат сохранён')
            old=TicketEvent.objects.create(organization=self.org,ticket=ticket,action='created',reason='Исходная запись')
            result=self.correct(ticket, description='Уточнение', contact_phone='+79990000000')
            self.assertEqual(result.status_code,200,result.data)
            ticket.refresh_from_db()
            self.assertEqual((ticket.status,ticket.priority,ticket.assigned_to_id,ticket.repair), (state,'ENTRAPMENT',self.tech.pk,'Результат сохранён'))
            self.assertTrue(result.data['can_correct'])
            event=ticket.events.get(action='corrected')
            self.assertEqual(event.actor_id,self.owner.pk)
            self.assertIn('Ошибся при вводе',event.reason)
            old.refresh_from_db();self.assertEqual(old.reason,'Исходная запись')

    def test_rights_owner_duty_assignee_and_shift_expiry(self):
        ticket=self.ticket(status='IN_PROGRESS')
        self.login(self.colleague)
        self.assertEqual(self.correct(ticket).status_code,403)
        now=timezone.now()
        shift=DutyShift.objects.create(organization=self.org,technician=self.second,start=now-timedelta(hours=1),end=now+timedelta(hours=1))
        self.assertEqual(self.correct(ticket).status_code,200)
        ticket.refresh_from_db()
        DutyShift.objects.filter(pk=shift.pk).update(end=now-timedelta(seconds=1))
        self.assertEqual(self.correct(ticket).status_code,403)
        self.login(self.worker)
        self.assertEqual(self.correct(ticket,description='Уточнил исполнитель').status_code,200)
        Ticket.objects.filter(pk=ticket.pk).update(status='DONE')
        self.assertEqual(self.correct(ticket).status_code,403)

    def test_stale_form_cannot_overwrite_and_invalid_fields_are_atomic(self):
        ticket=self.ticket()
        self.assertEqual(self.correct(ticket).status_code,200)
        self.assertEqual(self.correct(ticket,description='Устаревшая форма').status_code,409)
        ticket.refresh_from_db()
        for fields in ({'status':'DONE'},{'priority':'NORMAL'},{'assigned_to':self.second.pk},{'elevator':None},{'repair':'Подменённый результат'},{'reason':' '},{'title':''},{'contact_phone':'x'*100},{'expected_updated_at':'invalid'}):
            result=self.correct(ticket, **fields)
            self.assertIn(result.status_code,(400,409),result.data)
        self.assertEqual(ticket.events.filter(action='corrected').count(),1)
        self.assertEqual(ticket.comments.count(),0)
        self.assertEqual(ticket.description,'')

    def test_tenant_and_revoked_membership(self):
        ticket=self.ticket()
        self.login(self.owner,self.other)
        self.assertEqual(self.correct(ticket).status_code,404)
        self.login(self.owner)
        Membership.objects.filter(user=self.owner,organization=self.org).update(active=False)
        self.assertEqual(self.correct(ticket).status_code,403)
