import uuid
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from . import tests_message_receipts as fixture
from .models import Building, Elevator, Ticket, Membership


class HomeConditionTests(TestCase):
    def setUp(self):
        fixture.MessageReceiptTests.setUp(self)
        self.client.force_authenticate(self.sender)
        self.building=Building.objects.create(organization=self.org,name='Дом',address='Ленина, 24')
        self.lift=Elevator.objects.create(organization=self.org,building=self.building,entrance='2')

    def ticket(self, lift=None, **values):
        return Ticket.objects.create(organization=self.org,building=self.building,elevator=lift or self.lift,
            title=values.pop('title','Проверка дверей'),**values)

    def condition(self):
        return self.client.get('/api/home/condition/',HTTP_X_ORGANIZATION_ID=str(self.org.pk))

    def test_rolling_week_counts_six_excludes_canceled_house_future_and_old(self):
        now=timezone.now()
        for i in range(5):self.ticket(status='DONE')
        self.assertEqual(self.condition().data['attention'],[])
        sixth=self.ticket()
        canceled=self.ticket(status='CANCELED')
        old=self.ticket();Ticket.objects.filter(pk=old.pk).update(created_at=now-timedelta(days=7,seconds=1))
        future=self.ticket();Ticket.objects.filter(pk=future.pk).update(created_at=now+timedelta(days=1))
        Ticket.objects.create(organization=self.org,building=self.building,title='Неизвестный лифт')
        data=self.condition().data
        self.assertEqual([(r['id'],r['count']) for r in data['attention']],[(self.lift.pk,6)])
        result=self.client.get(f'/api/home/attention/{self.lift.pk}/').data
        self.assertEqual(len(result['tickets']),6)
        self.assertTrue({canceled.pk,old.pk,future.pk}.isdisjoint(t['id'] for t in result['tickets']))
        self.lift.active=False;self.lift.save()
        self.assertEqual(self.condition().data['attention'],[])
        self.assertEqual(self.client.get(f'/api/home/attention/{self.lift.pk}/').status_code,404)

    def test_repairs_group_one_row_per_lift_and_keep_stopped_without_ticket(self):
        self.ticket(status='IN_PROGRESS');long=self.ticket(status='LONG_REPAIR',long_repair_reason='Ждём двигатель')
        self.ticket(status='NEW');self.ticket(status='DONE')
        other=Elevator.objects.create(organization=self.org,building=self.building,entrance='3',stopped_at=timezone.now(),stop_reason='Остановлен для проверки')
        data=self.condition().data['repairs']
        self.assertEqual(len(data),2)
        self.assertEqual(next(r for r in data if r['id']==self.lift.pk)['ticket_id'],long.pk)
        self.assertIsNone(next(r for r in data if r['id']==other.pk)['ticket_id'])
        Ticket.objects.filter(elevator=self.lift).update(status='DONE')
        self.assertEqual([r['id'] for r in self.condition().data['repairs']],[other.pk])

    def test_org_and_external_adjuster_scope(self):
        foreignhome=Building.objects.create(organization=self.other,name='Другой дом',address='Чужой адрес')
        foreignlift=Elevator.objects.create(organization=self.other,building=foreignhome)
        for _ in range(6):Ticket.objects.create(organization=self.other,building=foreignhome,elevator=foreignlift,title='Чужая заявка')
        self.assertEqual(self.condition().data['attention'],[])
        self.assertEqual(self.client.get(f'/api/home/attention/{foreignlift.pk}/').status_code,404)
        Membership.objects.filter(user=self.sender).update(role='ADJUSTER',can_commissioning=True)
        self.assertEqual(self.condition().status_code,403)
        self.client.force_authenticate(None);self.assertIn(self.condition().status_code,(401,403))

    def test_empty_entrapment_description_and_title_api_and_idempotent_sync(self):
        result=self.client.post('/api/tickets/',{'building':self.building.pk,'priority':'ENTRAPMENT','description':''},format='json')
        self.assertEqual(result.status_code,201,result.data)
        self.assertEqual((result.data['title'],result.data['description']),('Застревание',''))
        op={'id':str(uuid.uuid4()),'type':'create','occurred_at':timezone.now().isoformat(),'body':{'building':self.building.pk,'priority':'ENTRAPMENT','description':''}}
        first=self.client.post('/api/mobile/sync/',op,format='json');self.assertEqual(first.status_code,201,first.data)
        again=self.client.post('/api/mobile/sync/',op,format='json');self.assertEqual(again.status_code,200,again.data)
        self.assertEqual(first.data['ticket']['id'],again.data['ticket']['id'])
        self.assertEqual(self.client.post('/api/tickets/',{'building':self.building.pk,'priority':'NORMAL'},format='json').status_code,400)

    def test_release_changes_visible_title_without_closing_and_repairs_legacy_display(self):
        ticket=self.ticket(priority='ENTRAPMENT',status='IN_PROGRESS',title='Застревание: двери не открываются',accepted_at=timezone.now())
        response=self.client.post(f'/api/tickets/{ticket.pk}/change-type/',{'priority':'NORMAL','reason':'Люди освобождены, ремонт дверей','people_released':True},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual((response.data['priority'],response.data['status'],response.data['title']),('NORMAL','IN_PROGRESS','Ремонт: двери не открываются'))
        ticket.refresh_from_db();self.assertTrue(ticket.events.filter(action='type_changed',before='ENTRAPMENT',after='NORMAL').exists())
        # Previously changed tickets are corrected in every list/detail response without a data migration.
        Ticket.objects.filter(pk=ticket.pk).update(title='Застревание')
        self.assertEqual(self.client.get(f'/api/tickets/{ticket.pk}/').data['title'],'Ремонт')
        Ticket.objects.filter(pk=ticket.pk).update(title='Проверка кнопки')
        self.assertEqual(self.client.get(f'/api/tickets/{ticket.pk}/').data['title'],'Проверка кнопки')

    def test_new_transferred_repair_appears_once_and_disappears_when_closed(self):
        ticket=self.ticket(priority='ENTRAPMENT')
        response=self.client.post(f'/api/tickets/{ticket.pk}/transfer-to-repair/', {'people_released':True},format='json')
        self.assertEqual(response.status_code,200,response.data)
        ticket.refresh_from_db();self.assertEqual(ticket.status,'NEW')
        rows=self.condition().data['repairs']
        self.assertEqual([(r['ticket_id'],r['status']) for r in rows],[(ticket.pk,'NEW')])
        # Ordinary new calls and unconfirmed entrapments do not imply repair work.
        self.ticket(priority='NORMAL');self.ticket(priority='ENTRAPMENT')
        self.assertEqual(len(self.condition().data['repairs']),1)
        for state in ('DONE','CANCELED'):
            Ticket.objects.filter(pk=ticket.pk).update(status=state)
            self.assertEqual(self.condition().data['repairs'],[])
