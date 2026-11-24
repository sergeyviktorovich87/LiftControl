"""Read one recent authorized request; only invoked by the host service."""
import json
from django.core.management.base import BaseCommand
from core.system_updates import recent_request, VERSION_RE


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--after', type=int, default=0)

    def handle(self, *args, **options):
        row = recent_request(max(0,options['after']))
        result = None
        if row and isinstance(row.details,dict):
            action = row.details.get('action')
            target = row.details.get('target','')
            if (action == 'check' and target == '' or
                    action == 'install' and isinstance(target,str) and VERSION_RE.fullmatch(target)):
                result = {'id':row.pk,'action':action,'target':target}
        self.stdout.write(json.dumps(result))
