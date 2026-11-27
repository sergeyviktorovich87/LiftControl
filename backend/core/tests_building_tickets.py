import io
import uuid
import tempfile
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from .models import Organization, Membership, Technician, Building, Elevator, DutyShift, Ticket, TicketEvent, TicketComment

class BuildingTicketTests(TestCase):
    def setUp(self):
        self.company=Organization.objects.get(pk=1)
        self.other=Organization.objects.create(name='Другая организация')
        self.home=Building.objects.create(name='Дом',address='Игнатьевское шоссе, 14')
        self.home2=Building.objects.create(name='Другой дом',address='Другая улица, 1')
        self.foreign=Building.objects.create(organization=self.other,name='Чужой дом',address='Чужой, 2')
        self.lift=Elevator.objects.create(building=self.home, factory_number='ONE')
        self.wrong=Elevator.objects.create(building=self.home2, factory_number='TWO')
        self.foreignlift=Elevator.objects.create(organization=self.other,building=self.foreign,factory_number='OTHER')
        self.worker=Technician.objects.create(full_name='Дежурный')
        self.admin=self.user('admin','ADMIN')
        self.mechanic=self.user('mechanic','MECHANIC',self.worker)
        self.stranger=self.user('stranger','MECHANIC',Technician.objects.create(full_name='Другой'))
        self.client=APIClient();self.client.force_authenticate(self.admin)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        settings=override_settings(MEDIA_ROOT=self.temp.name);settings.enable();self.addCleanup(settings.disable)
    def user(self,name,role,worker=None):
        user=get_user_model().objects.create_user(username=name,password='long-password')
        Membership.objects.create(user=user,organization=self.company,role=role,technician=worker)
        return user
    def post(self,path,body):
        return self.client.post('/api/'+path,body,format='json')
    def create(self,**extra):
        return self.post('tickets/',{'building':self.home.pk,'elevator':None,'title':'Не вызывается','description':'Какой лифт — неизвестно','entrance_hint':'2','floor_hint':'1',**extra})
    def duty(self):
        now=timezone.now();DutyShift.objects.create(organization=self.company,technician=self.worker,start=now-timedelta(hours=1),end=now+timedelta(hours=12))
    def test_house_ticket_serializes_notifies_and_accepts_without_fake_lift(self):
        self.duty();response=self.create(priority='ENTRAPMENT',contact_name='Житель',contact_phone='+70000000000')
        self.assertEqual(response.status_code,201,response.data)
        data=response.data;self.assertIsNone(data['elevator']);self.assertEqual(data['address'],self.home.address)
        self.assertEqual(data['elevator_label'],'Лифт не уточнён');self.assertEqual(Elevator.objects.count(),3)
        row=Ticket.objects.get(pk=data['id']);self.assertTrue(row.events.filter(action='created').exists())
        from .notification_content import ticket_text
        self.assertIn(self.home.address,ticket_text(row.events.get(action='created')))
        self.assertTrue(row.delivery_receipts.filter(recipient=self.mechanic).exists())
        self.client.force_authenticate(self.mechanic)
        self.assertEqual(self.post(f'tickets/{row.pk}/accept/',{}).status_code,200)
        self.assertEqual(self.post(f'tickets/{row.pk}/stop/',{'reason':'Неизвестно какой лифт'}).status_code,403)
        self.assertEqual(self.post(f'tickets/{row.pk}/complete/',{'work_description':'Осмотрен дом, ложный вызов','people_released':True}).status_code,200)
    def test_identify_keeps_history_and_never_moves_to_another_house(self):
        row=self.create().data;pk=row['id']
        TicketComment.objects.create(organization=self.company,ticket_id=pk,author=self.admin,body='Звонок жителя')
        for wrong in [self.wrong.pk,self.foreignlift.pk,0,'1']:
            self.assertEqual(self.post(f'tickets/{pk}/identify-lift/',{'elevator':wrong}).status_code,400)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.post(f'tickets/{pk}/identify-lift/',{'elevator':self.lift.pk}).status_code,403)
        self.duty();self.client.force_authenticate(self.mechanic)
        self.assertEqual(self.post(f'tickets/{pk}/accept/',{}).status_code,200)
        result=self.post(f'tickets/{pk}/identify-lift/',{'elevator':self.lift.pk});self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.data['id'],pk);self.assertEqual(result.data['elevator'],self.lift.pk)
        self.assertEqual(TicketComment.objects.filter(ticket_id=pk).count(),1)
        self.assertEqual(TicketEvent.objects.filter(ticket_id=pk,action='lift_identified').count(),1)
        self.assertEqual(self.post(f'tickets/{pk}/identify-lift/',{'elevator':self.lift.pk}).status_code,403)
    def test_address_required_and_tenant_and_building_lift_match_enforced(self):
        for payload in [{'title':'Нет адреса'},{'building':self.foreign.pk,'title':'Чужой дом'}, {'building':self.home.pk,'elevator':self.wrong.pk,'title':'Не тот дом'}]:
            response=self.post('tickets/',payload);self.assertEqual(response.status_code,400,response.data)
        legacy=self.post('tickets/',{'elevator':self.lift.pk,'title':'Старый клиент'})
        self.assertEqual(legacy.status_code,201,legacy.data);self.assertEqual(legacy.data['building'],self.home.pk)
    def test_same_operation_replays_house_creation_and_author_can_attach_photo(self):
        self.duty();self.client.force_authenticate(self.mechanic)
        command={'id':str(uuid.uuid4()),'type':'create','occurred_at':timezone.now().isoformat(),'body':{'building':self.home.pk,'elevator':None,'title':'На дом'}}
        first=self.post('mobile/sync/',command);self.assertEqual(first.status_code,201,first.data)
        again=self.post('mobile/sync/',command);self.assertTrue(again.data['replayed']);self.assertEqual(Ticket.objects.count(),1)
        pk=first.data['ticket']['id'];image=io.BytesIO();Image.new('RGB',(4,4),'green').save(image,format='PNG')
        response=self.client.post('/api/media/uploads/',{'kind':'ticket','target_id':pk,'upload_id':str(uuid.uuid4()),'category':'OTHER','file':SimpleUploadedFile('request.png',image.getvalue(),content_type='image/png')},format='multipart')
        self.assertEqual(response.status_code,201,response.data);self.assertEqual(Ticket.objects.get(pk=pk).photos.count(),1)
        self.client.force_authenticate(self.stranger)
        denied=self.client.post('/api/media/uploads/',{'kind':'ticket','target_id':pk,'upload_id':str(uuid.uuid4()),'file':SimpleUploadedFile('request.png',image.getvalue(),content_type='image/png')},format='multipart')
        self.assertEqual(denied.status_code,403)
    def test_unknown_completion_does_not_clear_other_elevator_stop(self):
        self.duty();self.lift.stopped_at=timezone.now();self.lift.stop_reason='Неисправность';self.lift.save()
        pk=self.create(assigned_to=self.worker.pk).data['id'];self.client.force_authenticate(self.mechanic)
        self.assertEqual(self.post(f'tickets/{pk}/accept/',{}).status_code,200)
        self.assertEqual(self.post(f'tickets/{pk}/complete/',{'work_description':'Проверен дом, обращение закрыто'}).status_code,200)
        self.lift.refresh_from_db();self.assertIsNotNone(self.lift.stopped_at)
