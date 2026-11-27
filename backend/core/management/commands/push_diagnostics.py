"""Safe support output: booleans, counts and times; no endpoints, keys or bodies."""
import json
import os
from django.core.management.base import BaseCommand
from django.db.models import Count,Min,Max
from django.utils import timezone
from core.push_notifications import push_config
from core.models import PushDelivery,PlanningPushDelivery,PersonalTaskPush,PushSubscription
class Command(BaseCommand):
    help='Show redacted push queue health. Run in API and push-worker containers.'
    def handle(self,*args,**kwargs):
        config=push_config();result={'time':timezone.now().isoformat(),'webpush_enabled':config['enabled'],'private_key_exists':bool(config['private_file'] and os.path.isfile(config['private_file'])),'private_key_readable':bool(config['private_file'] and os.access(config['private_file'],os.R_OK)),'subscriptions':PushSubscription.objects.count(),'queues':{}}
        result['vapid_pair_matches']=None
        if result['private_key_readable']:
            try:
                import base64
                from pathlib import Path
                from cryptography.hazmat.primitives import serialization as s
                key=s.load_pem_private_key(Path(config['private_file']).read_bytes(),None)
                actual=base64.urlsafe_b64encode(key.public_key().public_bytes(s.Encoding.X962,s.PublicFormat.UncompressedPoint)).rstrip(b'=').decode()
                result['vapid_pair_matches']=actual==config['public_key']
            except Exception:
                result['vapid_pair_matches']=False
        for name,model in [('tickets',PushDelivery),('inbox',PlanningPushDelivery),('tasks',PersonalTaskPush)]:
            rows=model.objects.all();result['queues'][name]={'states':list(rows.values('state').annotate(count=Count('pk'))),'pending_due':rows.filter(state__in=['PENDING','PROCESSING'],next_attempt_at__lte=timezone.now()).count(),'next_attempt':str(rows.filter(state__in=['PENDING','PROCESSING']).aggregate(first=Min('next_attempt_at'))['first'])}
        self.stdout.write(json.dumps(result,ensure_ascii=False,indent=2))
