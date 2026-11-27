from datetime import timedelta
from django.utils import timezone
from . import tests_field_ops as fixture
from .models import Ticket, DutyShift, Building, Membership
from .media_vault import may_link


class DutyCompletionTests(fixture.TestCase):
    setUp=fixture.FieldOperationsTests.setUp
    login=fixture.FieldOperationsTests.login

    def duty(self):
        now=timezone.now()
        self.shift=DutyShift.objects.create(organization=self.org,technician=self.second,start=now-timedelta(hours=1),end=now+timedelta(hours=1))
        self.login(self.colleague)

    def ticket(self, **values):
        return Ticket.objects.create(organization=self.org,building=self.lift.building,elevator=self.lift,
            assigned_to=self.tech,created_by=self.owner,title='Застревание',**values)

    def post(self,ticket,action,body):
        return self.client.post(f'/api/tickets/{ticket.pk}/{action}/',body,format='json',HTTP_X_ORGANIZATION_ID=str(self.org.pk))

    def test_duty_can_finish_new_other_assignment_with_true_release_and_own_result(self):
        ticket=self.ticket(priority='ENTRAPMENT')
        self.duty();body={'work_description':'Освободил людей, очистил контакты и проверил двери','people_released':True}
        self.assertEqual(self.post(ticket,'complete',{**body,'people_released':False}).status_code,400)
        self.assertEqual(self.post(ticket,'complete',{**body,'people_released':'true'}).status_code,400)
        self.assertEqual(self.post(ticket,'complete',{**body,'work_description':' '}).status_code,400)
        result=self.post(ticket,'complete',body);self.assertEqual(result.status_code,200,result.data)
        ticket.refresh_from_db();self.assertEqual((ticket.status,ticket.assigned_to_id,ticket.accepted_at),('DONE',self.tech.pk,None))
        self.assertIsNotNone(ticket.completed_at)
        comment=ticket.comments.get(kind='RESULT');self.assertEqual((comment.author_id,comment.body),(self.colleague.pk,body['work_description']))
        event=ticket.events.get(action='completed');self.assertEqual((event.actor_id,event.before,event.after),(self.colleague.pk,'NEW','DONE'))
        self.assertFalse(ticket.events.filter(action='accepted').exists())
        self.assertEqual(self.post(ticket,'complete',body).status_code,200)
        self.assertEqual(ticket.comments.filter(kind='RESULT').count(),1)
        self.assertEqual(ticket.events.filter(action='completed').count(),1)
        self.assertEqual(self.post(ticket,'complete',{**body,'work_description':'Другой результат'}).status_code,403)

    def test_completion_right_does_not_grant_stop_defer_resume_and_allows_photos(self):
        ticket=self.ticket(status='IN_PROGRESS',priority='NORMAL',accepted_at=timezone.now())
        self.duty();data=self.client.get(f'/api/tickets/{ticket.pk}/').data
        self.assertTrue(data['can_complete']);self.assertFalse(data['can_record_work']);self.assertFalse(data['can_stop']);self.assertFalse(data['can_resume'])
        may_link(self.colleague,'ticket',ticket)
        self.assertEqual(self.post(ticket,'stop',{'reason':'Остановить чужую заявку'}).status_code,403)
        self.assertEqual(self.post(ticket,'long-repair',{'reason':'Отложить чужую заявку'}).status_code,403)
        self.assertEqual(self.post(ticket,'complete',{'work_description':'Заменил контакт и проверил лифт'}).status_code,200)

    def test_end_of_shift_revocation_and_tenant_are_rechecked(self):
        ticket=self.ticket(status='IN_PROGRESS')
        self.duty();DutyShift.objects.filter(pk=self.shift.pk).update(end=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.post(ticket,'complete',{'work_description':'Нет действующей смены'}).status_code,403)
        self.login(self.owner);self.assertEqual(self.post(ticket,'complete',{'work_description':'Руководитель не исполнитель'}).status_code,403)
        self.login(self.worker);self.assertEqual(self.post(ticket,'complete',{'work_description':'Исполнитель закончил ремонт'}).status_code,200)
        foreign_home=Building.objects.create(organization=self.other,address='Чужой дом')
        other=Ticket.objects.create(organization=self.other,building=foreign_home,title='Чужая заявка')
        self.login(self.colleague)
        self.assertEqual(self.post(other,'complete',{'work_description':'Другая организация'}).status_code,404)
        Membership.objects.filter(user=self.colleague,organization=self.org).update(active=False)
        self.assertEqual(self.post(self.ticket(),'complete',{'work_description':'Доступ отозван'}).status_code,403)

    def test_transfer_optional_description_preserves_assignment_and_state(self):
        ticket=self.ticket(priority='ENTRAPMENT',status='IN_PROGRESS',accepted_at=timezone.now())
        accepted=ticket.accepted_at;self.duty()
        self.assertEqual(self.post(ticket,'transfer-to-repair',{}).status_code,400)
        body={'people_released':True,'description':''}
        result=self.post(ticket,'transfer-to-repair',body);self.assertEqual(result.status_code,200,result.data)
        ticket.refresh_from_db();self.assertEqual((ticket.priority,ticket.status,ticket.assigned_to_id,ticket.accepted_at),('NORMAL','IN_PROGRESS',self.tech.pk,accepted))
        self.assertIsNone(ticket.completed_at);self.assertEqual(ticket.comments.filter(kind='RESULT').count(),0)
        event=ticket.events.get(action='type_changed');self.assertEqual(event.actor_id,self.colleague.pk);self.assertIn('Люди освобождены',event.reason)
        self.assertEqual(self.post(ticket,'transfer-to-repair',body).status_code,200)
        self.assertEqual(ticket.events.filter(action='type_changed').count(),1)

    def test_transfer_description_and_closed_guard(self):
        ticket=self.ticket(priority='ENTRAPMENT')
        self.duty();body={'people_released':True,'description':'Не закрываются двери'}
        self.assertEqual(self.post(ticket,'transfer-to-repair',{**body,'description':'x'*901}).status_code,400)
        result=self.post(ticket,'transfer-to-repair',body);self.assertEqual(result.status_code,200,result.data)
        self.assertEqual((result.data['title'],result.data['status']),('Не закрываются двери','NEW'))
        self.assertIn(body['description'],ticket.events.get(action='type_changed').reason)
        Ticket.objects.filter(pk=ticket.pk).update(status='CANCELED',priority='ENTRAPMENT')
        self.assertEqual(self.post(ticket,'transfer-to-repair',body).status_code,403)
