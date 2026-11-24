"""Isolated SQLite fixture for documentation UI regression; never run on a production DB."""
import json
from django.contrib.auth import get_user_model
from django.test import Client
from core.models import Organization, Building, Elevator, DocumentFolder
u = get_user_model().objects.create_superuser('ui-folder-test', password='local-test-only')
organization = Organization.objects.get(pk=1)
building = Building.objects.create(organization=organization, name='ПИК', address='50 лет Октября, 265')
elevator = Elevator.objects.create(organization=organization, building=building, entrance='1',
                       manufacturer='МЭЛ', documentation_tags='мэл, monarch')
folder = DocumentFolder.objects.create(organization=organization, name='Электросхемы', elevator=elevator, documentation_tags='мэл, monarch')
DocumentFolder.objects.create(organization=organization, name='Архив', parent=folder)
client = Client()
client.force_login(u)
with open('/tmp/lift-ui-cookie.json', 'w') as target:
    json.dump([{'name': 'sessionid', 'value': client.cookies['sessionid'].value,
                'domain': '127.0.0.1', 'path': '/'}], target)
