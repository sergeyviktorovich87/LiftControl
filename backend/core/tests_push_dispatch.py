import threading
from django.test import SimpleTestCase
from .push_dispatch import dispatch


class DeliveryConcurrencyTests(SimpleTestCase):
    def test_slow_device_does_not_hold_up_the_next_device(self):
        delivered=threading.Event()
        def send(row):
            if row==0:
                self.assertTrue(delivered.wait(3),'Another device must be delivered while the first is blocked')
            else:
                delivered.set()
        dispatch([0,1],send,parallel=True)

    def test_concurrent_send_count_is_bounded(self):
        barrier=threading.Barrier(4,timeout=3)
        lock=threading.Lock();active=0;peak=0
        def send(row):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            barrier.wait()
            with lock:active-=1
        dispatch(range(12),send,parallel=True)
        self.assertEqual(peak,4)


from unittest.mock import patch
from django.db import connection
from django.test import TransactionTestCase
from unittest import skipUnless
from . import tests_push_reliability as reliability
from .models import PushDelivery,Organization
from .push_notifications import process_batch


@skipUnless(connection.vendor=='postgresql','Concurrent committed claims require PostgreSQL')
class PostgreSQLDispatchTests(TransactionTestCase):
    def setUp(self):
        Organization.objects.get_or_create(pk=1,defaults={"name":"Эверест"})
        reliability.PushReliabilityTests.setUp(self)
    user=reliability.PushReliabilityTests.user
    ticket=reliability.PushReliabilityTests.ticket

    def test_committed_claims_can_be_delivered_from_other_db_connections(self):
        self.ticket();self.ticket()
        barrier=threading.Barrier(2,timeout=5)
        def send(row,config):
            self.assertEqual(PushDelivery.objects.get(pk=row.pk).state,'PROCESSING')
            barrier.wait()
            return 'SENT'
        with patch('core.push_notifications.push_config',return_value=self.config),patch('core.push_notifications.deliver_one',side_effect=send):
            self.assertEqual(process_batch(parallel=True),2)
        self.assertEqual(PushDelivery.objects.filter(state='SENT').count(),2)
