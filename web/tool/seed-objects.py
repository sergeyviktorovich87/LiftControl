import json
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from core.models import Organization,Membership,Building,Elevator,Technician,Ticket
company=Organization.objects.get(pk=1)
user=get_user_model().objects.create_superuser(username='objects-ui-test',password='local-test-only')
Membership.objects.create(organization=company,user=user,role='ADMIN')
tech=Technician.objects.create(organization=company,full_name='Владимир Шатравка')
a=Building.objects.create(organization=company,name='Жилой дом',street='50 лет Октября',house='265/2',address='50 лет Октября, 265/2')
b=Building.objects.create(organization=company,name='Дом без лифтов',street='Ленина',house='17',address='Ленина, 17')
lift=Elevator.objects.create(organization=company,building=a,factory_number='OBJ-A',inventory_number='77',entrance='1',assigned_technician=tech,stopped_at=timezone.now(),stop_reason='Ремонт дверей')
archived=Elevator.objects.create(organization=company,building=a,factory_number='OBJ-B',entrance='2',active=False)
ticket=Ticket.objects.create(organization=company,building=a,elevator=lift,created_by=user,title='Застревание UI',priority='ENTRAPMENT',status='NEW')
client=Client();client.force_login(user)
open('/tmp/lift-objects-cookie.json','w').write(json.dumps([{'name':'sessionid','value':client.cookies['sessionid'].value,'domain':'127.0.0.1','path':'/','httpOnly':True,'secure':False,'sameSite':'Lax'}]))
open('/tmp/lift-objects-fixture.json','w').write(json.dumps({'building':a.pk,'lift':lift.pk,'archived':archived.pk,'ticket':ticket.pk}))
