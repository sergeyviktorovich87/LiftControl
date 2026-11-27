"""Bounded transport retries; no payloads or secret capability URLs in logs."""
import logging
from datetime import timedelta
from django.utils import timezone
log=logging.getLogger('liftcontrol.push')
MAX_ATTEMPTS=8

def retry_delay(attempt):
    return timedelta(seconds=(5,15,45,120,300,600)[max(0,min(int(attempt)-1,5))])


def confirmation_delay(attempt):
    # A provider ACK is not a display receipt. Retry soon, at most three sends.
    return timedelta(seconds=30 if attempt<=1 else 90)

def send(sub,payload,config,ttl=1800,urgent=False):
    import json
    from pywebpush import webpush,WebPushException
    payload=dict(payload)
    payload['title']=str(payload.get('title','Лифт Контроль'))[:120]
    payload['body']=str(payload.get('body','')).encode('utf-8')[:2000].decode('utf-8','ignore')
    while len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))>3000 and payload['body']:
        payload['body']=payload['body'][:-80]
    try:
        webpush(subscription_info={'endpoint':sub.endpoint,'keys':{'p256dh':sub.p256dh,'auth':sub.auth}},data=json.dumps(payload,ensure_ascii=False),vapid_private_key=config['private_file'],vapid_claims={'sub':config['subject']},ttl=max(60,int(ttl)),headers={'Urgency':'high' if urgent else 'normal'},timeout=8)
    except WebPushException as exc:
        code=getattr(exc,'status_code',None) or getattr(getattr(exc,'response',None),'status_code',None)
        if code in (404,410):sub.delete();return 'EXPIRED'
        log.warning('webpush_transport_failed http=%s',code)
        return 'FAILED' if code in (400,413) else 'RETRY'
    except Exception as exc:
        log.warning('webpush_transport_failed error=%s',type(exc).__name__)
        return 'RETRY'
    return 'SENT'
