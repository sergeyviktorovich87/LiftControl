from django.test import TestCase
from . import tests_push_reliability as fixture
from .models import Building,Elevator,Ticket,LiftDocument,AuditEvent


class ObjectDeletionTests(TestCase):
    setUp=fixture.PushReliabilityTests.setUp
    user=fixture.PushReliabilityTests.user
    ticket=fixture.PushReliabilityTests.ticket
    body={'reason':'Ошибочно созданный объект','confirm':True}

    def test_archived_lift_can_be_removed_without_erasing_history_or_files(self):
        ticket=self.ticket();self.lift.active=False;self.lift.save()
        doc=LiftDocument.objects.create(organization=self.company,elevator=self.lift,category='INSPECTION',title='Акт',file='keep.pdf')
        result=self.client.delete(f'/api/elevators/{self.lift.pk}/',self.body,format='json');self.assertEqual(result.status_code,204,result.data)
        self.lift.refresh_from_db();self.assertIsNotNone(self.lift.deleted_at)
        self.assertFalse(any(row['id']==self.lift.pk for row in self.client.get('/api/elevators/').data))
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).status,'NEW');self.assertTrue(LiftDocument.objects.filter(pk=doc.pk).exists())
        self.assertEqual(self.client.get(f'/api/tickets/{ticket.pk}/').data['address'],self.lift.building.address)
        self.assertEqual(self.client.get(f'/api/elevators/{self.lift.pk}/').status_code,200)
        self.assertEqual(self.client.patch(f'/api/elevators/{self.lift.pk}/',{'active':True},format='json').status_code,404)

    def test_house_removes_active_and_archived_lifts_and_keeps_open_tickets(self):
        ticket=self.ticket();archived=Elevator.objects.create(organization=self.company,building=self.lift.building,factory_number='ARCHIVED',active=False)
        path=f'/api/buildings/{self.lift.building_id}/'
        self.assertEqual(self.client.delete(path).status_code,400)
        response=self.client.delete(path,self.body,format='json');self.assertEqual(response.status_code,204,response.data)
        self.assertEqual(Elevator.objects.filter(building=self.lift.building,deleted_at__isnull=False,active=False).count(),2)
        self.assertFalse(any(b['id']==self.lift.building_id for b in self.client.get('/api/buildings/').data))
        self.assertEqual(self.client.get('/api/elevators/').data,[])
        self.assertTrue(Ticket.objects.filter(pk=ticket.pk,status='NEW').exists())
        self.assertTrue(AuditEvent.objects.filter(action='building.deleted',object_id=str(self.lift.building_id)).exists())
        result=self.client.post('/api/elevators/',{'building':self.lift.building_id,'factory_number':'LATE'},format='json');self.assertEqual(result.status_code,400,result.data)
        result=self.client.post('/api/tickets/',{'building':self.lift.building_id,'title':'Поздняя заявка'},format='json');self.assertEqual(result.status_code,400,result.data)

    def test_numbers_can_be_reused_after_removal_but_not_while_live(self):
        original=self.lift.factory_number
        self.assertEqual(self.client.post('/api/elevators/',{'building':self.lift.building_id,'factory_number':original},format='json').status_code,400)
        self.assertEqual(self.client.delete(f'/api/elevators/{self.lift.pk}/',self.body,format='json').status_code,204)
        response=self.client.post('/api/elevators/',{'building':self.lift.building_id,'factory_number':original},format='json');self.assertEqual(response.status_code,201,response.data)
        self.assertNotEqual(response.data['id'],self.lift.pk)

    def test_deletion_is_owner_only_tenant_scoped_and_cannot_be_spoofed(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.delete(f'/api/elevators/{self.lift.pk}/',self.body,format='json').status_code,403)
        self.client.force_authenticate(self.admin)
        foreign=fixture.Organization.objects.create(name='Другая');home=Building.objects.create(organization=foreign,name='Чужой дом',address='Чужой адрес')
        self.assertEqual(self.client.delete(f'/api/buildings/{home.pk}/',self.body,format='json').status_code,404)
        response=self.client.patch(f'/api/elevators/{self.lift.pk}/',{'deleted_at':'2026-11-27T00:00:00Z'},format='json');self.assertEqual(response.status_code,200,response.data)
        self.lift.refresh_from_db();self.assertIsNone(self.lift.deleted_at)
